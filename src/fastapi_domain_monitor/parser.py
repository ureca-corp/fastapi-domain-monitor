"""
Python AST 기반 소스 코드 파서.
import/실행 없이 안전하게 파싱.
"""
from __future__ import annotations

import ast
from pathlib import Path

from fastapi_domain_monitor.models import (
    DomainSchema,
    ParsedClass,
    ParsedEnum,
    ParsedField,
    ParsedModule,
    ParsedRelationship,
)


# ── 헬퍼 ─────────────────────────────────────────────────────


def _extract_type_info(node: ast.expr | None) -> tuple[str, bool, bool]:
    """타입 어노테이션 노드에서 (type_str, is_nullable, is_list) 추출."""
    if node is None:
        return ("", False, False)

    # str | None → BinOp(BitOr)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        if isinstance(node.right, ast.Constant) and node.right.value is None:
            type_str, _, is_list = _extract_type_info(node.left)
            return (type_str, True, is_list)
        if isinstance(node.left, ast.Constant) and node.left.value is None:
            type_str, _, is_list = _extract_type_info(node.right)
            return (type_str, True, is_list)
        left_str, _, _ = _extract_type_info(node.left)
        right_str, _, _ = _extract_type_info(node.right)
        return (f"{left_str} | {right_str}", False, False)

    # Optional["X"], list["X"]
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        name = node.value.id
        if name == "Optional":
            inner_str, _, is_list = _extract_type_info(node.slice)
            return (inner_str, True, is_list)
        if name == "list":
            inner_str, _, _ = _extract_type_info(node.slice)
            return (inner_str, False, True)
        return (ast.unparse(node), False, False)

    # 단순 이름: str, UUID, Account …
    if isinstance(node, ast.Name):
        return (node.id, False, False)

    # forward reference: "Teacher"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value, False, False)

    return (ast.unparse(node), False, False)


def _get_keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _has_keyword(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _get_keyword_bool(call: ast.Call, name: str) -> bool:
    val = _get_keyword_value(call, name)
    return isinstance(val, ast.Constant) and val.value is True


def _get_keyword_str(call: ast.Call, name: str) -> str | None:
    val = _get_keyword_value(call, name)
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    return None


def _is_call_named(node: ast.expr | None, func_name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == func_name
    )


def _check_sa_column_json(call: ast.Call) -> bool:
    """Field(sa_column=Column(JSON)) 패턴에서 JSON 감지."""
    sa_col = _get_keyword_value(call, "sa_column")
    if isinstance(sa_col, ast.Call):
        for arg in sa_col.args:
            if isinstance(arg, ast.Name) and arg.id == "JSON":
                return True
    return False


def _check_uselist_false(call: ast.Call) -> bool:
    """sa_relationship_kwargs={"uselist": False} 감지."""
    sa_kwargs = _get_keyword_value(call, "sa_relationship_kwargs")
    if isinstance(sa_kwargs, ast.Dict):
        for key, val in zip(sa_kwargs.keys, sa_kwargs.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "uselist"
                and isinstance(val, ast.Constant)
                and val.value is False
            ):
                return True
    return False


# ── 필드 / 관계 파싱 ─────────────────────────────────────────


def _parse_field(node: ast.AnnAssign) -> ParsedField | None:
    if not isinstance(node.target, ast.Name):
        return None
    name = node.target.id
    if name.startswith("__"):
        return None

    type_str, is_nullable, is_list = _extract_type_info(node.annotation)
    if is_list:
        type_str = f"list[{type_str}]"

    pf = ParsedField(name=name, type_annotation=type_str, is_nullable=is_nullable)

    if node.value and _is_call_named(node.value, "Field"):
        call = node.value
        pf.is_primary_key = _get_keyword_bool(call, "primary_key")
        pf.foreign_key = _get_keyword_str(call, "foreign_key")
        pf.has_default = _has_keyword(call, "default") or _has_keyword(call, "default_factory")
        pf.is_sa_column = _has_keyword(call, "sa_column")
        pf.is_json = _check_sa_column_json(call)
    elif node.value is not None and not _is_call_named(node.value, "Relationship"):
        pf.has_default = True

    return pf


def _parse_relationship(node: ast.AnnAssign) -> ParsedRelationship | None:
    if not isinstance(node.target, ast.Name):
        return None
    if not node.value or not _is_call_named(node.value, "Relationship"):
        return None

    field_name = node.target.id
    type_str, _, is_list = _extract_type_info(node.annotation)
    call = node.value

    link_model_val = _get_keyword_value(call, "link_model")
    link_model = link_model_val.id if isinstance(link_model_val, ast.Name) else None

    return ParsedRelationship(
        field_name=field_name,
        target_class=type_str,
        back_populates=_get_keyword_str(call, "back_populates"),
        is_list=is_list,
        link_model=link_model,
        uselist_false=_check_uselist_false(call),
    )


# ── 클래스 / Enum 파싱 ───────────────────────────────────────


def _is_enum_class(cls_node: ast.ClassDef) -> bool:
    return any(
        isinstance(b, ast.Name) and b.id.endswith("Enum") for b in cls_node.bases
    )


def _parse_enum(cls_node: ast.ClassDef) -> ParsedEnum:
    base_class = ""
    for base in cls_node.bases:
        if isinstance(base, ast.Name):
            base_class = base.id
            break

    members = []
    for item in cls_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    members.append(target.id)

    return ParsedEnum(name=cls_node.name, base_class=base_class, members=members)


def _parse_class(cls_node: ast.ClassDef) -> ParsedClass:
    base_classes = [b.id for b in cls_node.bases if isinstance(b, ast.Name)]

    is_table = any(
        kw.arg == "table" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in cls_node.keywords
    )

    docstring = None
    if (
        cls_node.body
        and isinstance(cls_node.body[0], ast.Expr)
        and isinstance(cls_node.body[0].value, ast.Constant)
        and isinstance(cls_node.body[0].value.value, str)
    ):
        docstring = cls_node.body[0].value.value

    tablename = None
    fields: list[ParsedField] = []
    relationships: list[ParsedRelationship] = []

    for item in cls_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "__tablename__":
                    if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                        tablename = item.value.value

        if isinstance(item, ast.AnnAssign):
            rel = _parse_relationship(item)
            if rel:
                relationships.append(rel)
            else:
                pf = _parse_field(item)
                if pf:
                    fields.append(pf)

    return ParsedClass(
        name=cls_node.name,
        base_classes=base_classes,
        is_table=is_table,
        tablename=tablename,
        fields=fields,
        relationships=relationships,
        docstring=docstring,
    )


# ── 공개 API ─────────────────────────────────────────────────


def _extract_domain_name(file_path: Path) -> str:
    parts = file_path.parts
    for i, part in enumerate(parts):
        if part == "modules" and i + 1 < len(parts):
            return parts[i + 1]
    return file_path.parent.name


def parse_file(file_path: Path) -> ParsedModule:
    """단일 _models.py 파일 파싱."""
    file_path = Path(file_path)
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    module = ParsedModule(
        domain_name=_extract_domain_name(file_path),
        file_path=file_path,
    )

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if _is_enum_class(node):
                module.enums.append(_parse_enum(node))
            else:
                module.classes.append(_parse_class(node))

    return module


def parse_directory(
    watch_dirs: list[str | Path],
    base_path: Path | None = None,
) -> DomainSchema:
    """여러 디렉터리에서 *_models.py 패턴의 파일 찾아서 파싱."""
    schema = DomainSchema()

    for dir_path in watch_dirs:
        dir_path = Path(dir_path)
        if base_path and not dir_path.is_absolute():
            dir_path = base_path / dir_path

        if not dir_path.exists():
            continue

        for model_file in sorted(dir_path.rglob("*_models.py")):
            schema.modules.append(parse_file(model_file))

    return schema
