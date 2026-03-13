"""
Python AST 기반 소스 코드 파서.
import/실행 없이 안전하게 파싱.
"""
from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from fastapi_domain_monitor.models import (
    DomainSchema,
    ParsedClass,
    ParsedEnum,
    ParsedField,
    ParsedMethod,
    ParsedModule,
    ParsedRelationship,
    SourceSpan,
)

DEFAULT_WATCH_PATTERNS = (
    "*_models.py",
    "models.py",
    "*_schemas.py",
    "schemas.py",
    "*_entities.py",
    "entities.py",
    "*_dto.py",
    "dto.py",
)

FRAMEWORK_BASES = {"BaseModel", "SQLModel", "object"}
DTO_NAME_HINTS = ("dto", "schema", "request", "response", "payload")
CONFIG_KEYS = (
    "title",
    "extra",
    "frozen",
    "validate_assignment",
    "populate_by_name",
    "from_attributes",
    "str_strip_whitespace",
)
FIELD_CONSTRAINT_KEYS = (
    "primary_key",
    "index",
    "unique",
    "nullable",
    "min_length",
    "max_length",
    "ge",
    "gt",
    "le",
    "lt",
    "regex",
    "pattern",
    "description",
    "deprecated",
    "title",
    "repr",
    "exclude",
)
VALIDATOR_DECORATORS = {"field_validator", "model_validator"}
SERIALIZER_DECORATORS = {"field_serializer", "model_serializer"}


@dataclass
class TypeInfo:
    display: str
    nullable: bool = False
    collection_kind: str | None = None
    target_ref: str | None = None
    is_classvar: bool = False
    annotated_field_call: ast.Call | None = None


# ── 헬퍼 ─────────────────────────────────────────────────────


def _make_symbol_id(file_path: Path, symbol_name: str, kind: str) -> str:
    digest = hashlib.sha1(f"{file_path.resolve()}::{kind}::{symbol_name}".encode("utf-8")).hexdigest()
    return digest[:16]


def _make_source_span(file_path: Path, node: ast.AST) -> SourceSpan:
    return SourceSpan(
        file_path=file_path.resolve(),
        start_line=getattr(node, "lineno", 1),
        end_line=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
    )


def _extract_domain_name(file_path: Path) -> str:
    parts = file_path.parts
    for i, part in enumerate(parts):
        if part == "modules" and i + 1 < len(parts):
            return parts[i + 1]
    return file_path.parent.name


def _last_name(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _expr_to_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    return ast.unparse(node).strip()


def _visibility_for_name(name: str) -> str:
    if name.startswith("_"):
        return "private"
    return "public"


def _normalize_literal(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return repr(node.value) if isinstance(node.value, str) else str(node.value)
    return _expr_to_text(node)


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


def _get_keyword_literal_bool(call: ast.Call, name: str) -> bool | None:
    val = _get_keyword_value(call, name)
    if isinstance(val, ast.Constant) and isinstance(val.value, bool):
        return val.value
    return None


def _get_keyword_str(call: ast.Call, name: str) -> str | None:
    val = _get_keyword_value(call, name)
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    return None


def _is_call_named(node: ast.expr | None, func_name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        (isinstance(func, ast.Name) and func.id == func_name)
        or (isinstance(func, ast.Attribute) and func.attr == func_name)
    )


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return _expr_to_text(node) or ""


def _decorator_label(node: ast.expr) -> str:
    name = _decorator_name(node)
    if isinstance(node, ast.Call) and node.args:
        args = []
        for arg in node.args:
            value = _normalize_literal(arg)
            if value is not None:
                args.append(value.strip("'\""))
        if args:
            return f"{name}({', '.join(args)})"
    return name


def _dict_literal_items(node: ast.expr | None) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}

    data: dict[str, str] = {}
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            raw = _normalize_literal(value)
            if raw is not None:
                data[key.value] = raw.strip("'\"")
    return data


def _find_calls(node: ast.AST | None, func_name: str) -> list[ast.Call]:
    if node is None:
        return []
    return [
        child for child in ast.walk(node)
        if isinstance(child, ast.Call) and _is_call_named(child, func_name)
    ]


def _extract_type_info(node: ast.expr | None) -> TypeInfo:
    if node is None:
        return TypeInfo(display="")

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        if isinstance(node.right, ast.Constant) and node.right.value is None:
            inner = _extract_type_info(node.left)
            inner.nullable = True
            return inner
        if isinstance(node.left, ast.Constant) and node.left.value is None:
            inner = _extract_type_info(node.right)
            inner.nullable = True
            return inner
        left = _extract_type_info(node.left)
        right = _extract_type_info(node.right)
        return TypeInfo(display=f"{left.display} | {right.display}")

    if isinstance(node, ast.Name):
        return TypeInfo(display=node.id, target_ref=node.id)

    if isinstance(node, ast.Attribute):
        text = ast.unparse(node)
        return TypeInfo(display=text, target_ref=text)

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return TypeInfo(display=node.value, target_ref=node.value)

    if isinstance(node, ast.Subscript):
        outer = _last_name(node.value)
        if outer == "Annotated":
            items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            base_info = _extract_type_info(items[0]) if items else TypeInfo(display="")
            for meta in items[1:]:
                if isinstance(meta, ast.Call) and _is_call_named(meta, "Field"):
                    base_info.annotated_field_call = meta
                    break
            return base_info

        if outer == "Optional":
            inner = _extract_type_info(node.slice)
            inner.nullable = True
            return inner

        if outer == "ClassVar":
            inner = _extract_type_info(node.slice)
            inner.display = f"ClassVar[{inner.display}]"
            inner.is_classvar = True
            inner.target_ref = None
            inner.collection_kind = None
            return inner

        if outer in {"list", "List", "set", "Set"}:
            inner = _extract_type_info(node.slice)
            kind = outer.lower()
            return TypeInfo(
                display=f"{kind}[{inner.display}]",
                nullable=False,
                collection_kind=kind,
                target_ref=inner.target_ref,
            )

        if outer in {"dict", "Dict"}:
            values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            key_info = _extract_type_info(values[0]) if values else TypeInfo(display="Any")
            value_info = _extract_type_info(values[1]) if len(values) > 1 else TypeInfo(display="Any")
            return TypeInfo(
                display=f"dict[{key_info.display}, {value_info.display}]",
                collection_kind="dict",
                target_ref=value_info.target_ref,
            )

        return TypeInfo(display=ast.unparse(node))

    return TypeInfo(display=ast.unparse(node))


def _check_sa_column_json(call: ast.Call) -> bool:
    sa_col = _get_keyword_value(call, "sa_column")
    if isinstance(sa_col, ast.Call):
        for arg in sa_col.args:
            if isinstance(arg, ast.Name) and arg.id == "JSON":
                return True
            if isinstance(arg, ast.Attribute) and arg.attr == "JSON":
                return True
    return False


def _extract_ondelete_from_node(node: ast.AST | None) -> str | None:
    for foreign_key_call in _find_calls(node, "ForeignKey"):
        ondelete = _get_keyword_str(foreign_key_call, "ondelete")
        if ondelete:
            return ondelete
    return None


def _field_has_default(call: ast.Call) -> bool:
    if _has_keyword(call, "default") or _has_keyword(call, "default_factory"):
        return True
    if not call.args:
        return False
    first_arg = call.args[0]
    return not (isinstance(first_arg, ast.Constant) and first_arg.value is Ellipsis)


def _field_default_repr(call: ast.Call) -> tuple[str | None, str | None]:
    if _has_keyword(call, "default_factory"):
        factory = _expr_to_text(_get_keyword_value(call, "default_factory"))
        return (None, factory)
    if _has_keyword(call, "default"):
        return (_normalize_literal(_get_keyword_value(call, "default")), None)
    if call.args:
        first_arg = call.args[0]
        if not (isinstance(first_arg, ast.Constant) and first_arg.value is Ellipsis):
            return (_normalize_literal(first_arg), None)
    return (None, None)


def _field_nullable_override(call: ast.Call) -> bool | None:
    direct_nullable = _get_keyword_literal_bool(call, "nullable")
    if direct_nullable is not None:
        return direct_nullable

    sa_column_kwargs = _dict_literal_items(_get_keyword_value(call, "sa_column_kwargs"))
    if "nullable" in sa_column_kwargs:
        return sa_column_kwargs["nullable"] == "True"

    sa_col = _get_keyword_value(call, "sa_column")
    if isinstance(sa_col, ast.Call):
        return _get_keyword_literal_bool(sa_col, "nullable")

    return None


def _field_constraints(call: ast.Call) -> dict[str, str]:
    constraints: dict[str, str] = {}
    for key in FIELD_CONSTRAINT_KEYS:
        value = _get_keyword_value(call, key)
        if value is None:
            continue
        text = _normalize_literal(value)
        if text is None:
            continue
        constraints[key] = text.strip("'\"")
    return constraints


def _enum_ref_from_default_repr(default_repr: str | None) -> str | None:
    if not default_repr or "." not in default_repr:
        return None
    candidate = default_repr.split(".", 1)[0].strip("'\"")
    if not candidate or candidate in {"self", "cls"}:
        return None
    return candidate


def _extract_sa_enum_ref(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not _is_call_named(child, "SAEnum") and not _is_call_named(child, "Enum"):
            continue
        if not child.args:
            continue
        ref = _last_name(child.args[0])
        if ref:
            return ref
    return None


def _enum_ref_from_line_comment(source_lines: tuple[str, ...], node: ast.AST) -> str | None:
    line_number = getattr(node, "lineno", 0)
    if line_number <= 0 or line_number > len(source_lines):
        return None

    line = source_lines[line_number - 1]
    if "#" not in line:
        return None

    comment = line.split("#", 1)[1].strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", comment):
        return None
    return comment.rsplit(".", 1)[-1]


def _apply_field_call_metadata(field: ParsedField, call: ast.Call) -> None:
    field.is_primary_key = _get_keyword_bool(call, "primary_key")
    field.foreign_key = _get_keyword_str(call, "foreign_key")
    field.ondelete = _get_keyword_str(call, "ondelete") or _extract_ondelete_from_node(_get_keyword_value(call, "sa_column"))
    field.alias = _get_keyword_str(call, "alias")
    field.is_sa_column = _has_keyword(call, "sa_column")
    field.is_json = _check_sa_column_json(call)
    nullable_override = _field_nullable_override(call)
    if nullable_override is not None:
        field.is_nullable = nullable_override
    field.has_default = _field_has_default(call)
    field.default_repr, field.default_factory = _field_default_repr(call)
    field.constraints.update(_field_constraints(call))
    field.enum_ref_hint = _enum_ref_from_default_repr(field.default_repr) or _extract_sa_enum_ref(
        _get_keyword_value(call, "sa_column")
    )


def _check_uselist_false(call: ast.Call) -> bool:
    sa_kwargs = _dict_literal_items(_get_keyword_value(call, "sa_relationship_kwargs"))
    return sa_kwargs.get("uselist") == "False"


def _check_delete_orphan(call: ast.Call) -> bool:
    sa_kwargs = _dict_literal_items(_get_keyword_value(call, "sa_relationship_kwargs"))
    cascade = sa_kwargs.get("cascade", "")
    return "delete-orphan" in cascade


def _parse_field(node: ast.AnnAssign, source_lines: tuple[str, ...]) -> ParsedField | None:
    if not isinstance(node.target, ast.Name):
        return None

    name = node.target.id
    if name.startswith("__"):
        return None

    type_info = _extract_type_info(node.annotation)
    visibility = _visibility_for_name(name)
    field = ParsedField(
        name=name,
        type_annotation=type_info.display,
        visibility=visibility,
        is_nullable=type_info.nullable,
        is_private=visibility == "private",
        is_classvar=type_info.is_classvar,
        collection_kind=type_info.collection_kind,
    )

    field_call = node.value if _is_call_named(node.value, "Field") else type_info.annotated_field_call
    if isinstance(field_call, ast.Call):
        _apply_field_call_metadata(field, field_call)
    elif node.value is not None and not _is_call_named(node.value, "Relationship"):
        field.has_default = True
        field.default_repr = _normalize_literal(node.value)
        field.enum_ref_hint = _enum_ref_from_default_repr(field.default_repr)

    if _is_call_named(node.value, "PrivateAttr"):
        field.is_private = True
        field.visibility = "private"
        field.has_default = True
        field.default_repr = _normalize_literal(node.value.args[0]) if node.value.args else _normalize_literal(_get_keyword_value(node.value, "default"))
        field.default_factory = _expr_to_text(_get_keyword_value(node.value, "default_factory"))
        field.enum_ref_hint = _enum_ref_from_default_repr(field.default_repr)

    if field.enum_ref_hint is None:
        field.enum_ref_hint = _enum_ref_from_line_comment(source_lines, node)

    return field


def _parse_relationship(node: ast.AnnAssign) -> ParsedRelationship | None:
    if not isinstance(node.target, ast.Name):
        return None
    if not isinstance(node.value, ast.Call) or not _is_call_named(node.value, "Relationship"):
        return None

    type_info = _extract_type_info(node.annotation)
    link_model_val = _get_keyword_value(node.value, "link_model")
    if isinstance(link_model_val, ast.Name):
        link_model = link_model_val.id
    elif isinstance(link_model_val, ast.Attribute):
        link_model = ast.unparse(link_model_val)
    else:
        link_model = None

    return ParsedRelationship(
        field_name=node.target.id,
        target_class=type_info.target_ref or type_info.display,
        back_populates=_get_keyword_str(node.value, "back_populates"),
        is_list=type_info.collection_kind in {"list", "set"},
        collection_kind=type_info.collection_kind,
        link_model=link_model.rsplit(".", 1)[-1] if link_model else None,
        uselist_false=_check_uselist_false(node.value),
        cascade_delete=_get_keyword_bool(node.value, "cascade_delete"),
        has_delete_orphan=_check_delete_orphan(node.value),
    )


def _parameter_list(node: ast.FunctionDef, skip_first: bool) -> list[str]:
    args = list(node.args.posonlyargs) + list(node.args.args)
    if skip_first and args:
        args = args[1:]

    params = []
    for arg in args:
        annotation = _extract_type_info(arg.annotation).display if arg.annotation else "Any"
        params.append(f"{arg.arg}: {annotation}")
    for arg in node.args.kwonlyargs:
        annotation = _extract_type_info(arg.annotation).display if arg.annotation else "Any"
        params.append(f"{arg.arg}: {annotation}")
    if node.args.vararg:
        params.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        params.append(f"**{node.args.kwarg.arg}")
    return params


def _parse_method(node: ast.FunctionDef) -> tuple[ParsedMethod, ParsedField | None]:
    decorator_names = [_decorator_name(decorator) for decorator in node.decorator_list]
    decorator_labels = [_decorator_label(decorator) for decorator in node.decorator_list]
    is_staticmethod = "staticmethod" in decorator_names
    is_classmethod = "classmethod" in decorator_names or any(name in VALIDATOR_DECORATORS for name in decorator_names)
    visibility = _visibility_for_name(node.name)
    return_type = _extract_type_info(node.returns).display if node.returns else None

    method = ParsedMethod(
        name=node.name,
        parameters=_parameter_list(node, skip_first=not is_staticmethod),
        return_type=return_type,
        visibility=visibility,
        decorator_labels=decorator_labels,
        is_classmethod=is_classmethod,
        is_staticmethod=is_staticmethod,
        is_abstract="abstractmethod" in decorator_names,
        is_property=any(name in {"property", "cached_property"} for name in decorator_names),
        is_computed_field="computed_field" in decorator_names,
        is_validator=any(name in VALIDATOR_DECORATORS for name in decorator_names),
        is_serializer=any(name in SERIALIZER_DECORATORS for name in decorator_names),
    )

    synthetic_field = None
    if method.is_computed_field:
        synthetic_field = ParsedField(
            name=node.name,
            type_annotation=return_type or "Any",
            visibility=visibility,
            is_private=visibility == "private",
            is_computed=True,
        )

    return method, synthetic_field


def _self_field_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def _enum_ref_from_member_expr(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id
    return None


def _method_field_enum_hints(node: ast.FunctionDef) -> dict[str, set[str]]:
    hints: dict[str, set[str]] = defaultdict(set)

    for child in ast.walk(node):
        if isinstance(child, ast.Compare):
            left_field = _self_field_name(child.left)
            if left_field:
                for comparator in child.comparators:
                    enum_ref = _enum_ref_from_member_expr(comparator)
                    if enum_ref:
                        hints[left_field].add(enum_ref)

            for comparator in child.comparators:
                right_field = _self_field_name(comparator)
                if right_field:
                    enum_ref = _enum_ref_from_member_expr(child.left)
                    if enum_ref:
                        hints[right_field].add(enum_ref)

        elif isinstance(child, ast.Assign):
            enum_ref = _enum_ref_from_member_expr(child.value)
            if not enum_ref:
                continue
            for target in child.targets:
                field_name = _self_field_name(target)
                if field_name:
                    hints[field_name].add(enum_ref)

        elif isinstance(child, ast.AnnAssign):
            field_name = _self_field_name(child.target)
            enum_ref = _enum_ref_from_member_expr(child.value)
            if field_name and enum_ref:
                hints[field_name].add(enum_ref)

    return hints


def _config_from_call(node: ast.Call) -> dict[str, str]:
    config: dict[str, str] = {}
    for kw in node.keywords:
        if kw.arg is None:
            continue
        value = _normalize_literal(kw.value)
        if value is not None:
            config[kw.arg] = value.strip("'\"")
    return config


def _parse_config_assign(item: ast.Assign) -> dict[str, str]:
    if isinstance(item.value, ast.Call) and _is_call_named(item.value, "ConfigDict"):
        return _config_from_call(item.value)
    if isinstance(item.value, ast.Dict):
        return _dict_literal_items(item.value)
    return {}


def _parse_inner_config(node: ast.ClassDef) -> dict[str, str]:
    config: dict[str, str] = {}
    for item in node.body:
        if isinstance(item, ast.Assign):
            value = _normalize_literal(item.value)
            if value is None:
                continue
            for target in item.targets:
                if isinstance(target, ast.Name):
                    config[target.id] = value.strip("'\"")
    return config


def _compute_stereotypes(parsed_class: ParsedClass) -> list[str]:
    stereotypes: list[str] = []
    if parsed_class.is_join_table:
        stereotypes.append("JoinTable")
    elif parsed_class.is_table:
        stereotypes.append("Entity")
    elif any(base == "BaseModel" for base in parsed_class.base_classes) or any(hint in parsed_class.name.lower() for hint in DTO_NAME_HINTS):
        stereotypes.append("DTO")
    elif any(base in FRAMEWORK_BASES for base in parsed_class.base_classes):
        stereotypes.append("Abstract")
    else:
        stereotypes.append("ValueObject")

    if parsed_class.is_abstract:
        stereotypes.append("Abstract")
    return stereotypes


def _is_enum_class(cls_node: ast.ClassDef) -> bool:
    for base in cls_node.bases:
        base_name = _last_name(base)
        if base_name and base_name.endswith("Enum"):
            return True
    return False


def _parse_enum(cls_node: ast.ClassDef, file_path: Path) -> ParsedEnum:
    base_class = ""
    for base in cls_node.bases:
        base_name = _last_name(base)
        if base_name:
            base_class = base_name
            break

    members = []
    for item in cls_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    members.append(target.id)

    all_bases = [b for base in cls_node.bases if (b := _last_name(base))]
    return ParsedEnum(
        name=cls_node.name,
        symbol_id=_make_symbol_id(file_path, cls_node.name, "enum"),
        source_span=_make_source_span(file_path, cls_node),
        base_class=base_class,
        members=members,
        base_classes=all_bases,
    )


def _parse_class(cls_node: ast.ClassDef, file_path: Path, source_lines: tuple[str, ...]) -> ParsedClass:
    base_classes = []
    for base in cls_node.bases:
        base_name = _last_name(base)
        if base_name:
            base_classes.append(base_name)

    is_table = any(
        kw.arg == "table" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in cls_node.keywords
    )
    is_protocol_like = "Protocol" in base_classes
    docstring = ast.get_docstring(cls_node)
    parsed_class = ParsedClass(
        name=cls_node.name,
        symbol_id=_make_symbol_id(file_path, cls_node.name, "class"),
        source_span=_make_source_span(file_path, cls_node),
        base_classes=base_classes,
        is_table=is_table,
        docstring=docstring,
        is_protocol_like=is_protocol_like,
    )
    method_enum_hints: dict[str, set[str]] = defaultdict(set)

    for item in cls_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "__tablename__":
                    if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                        parsed_class.tablename = item.value.value
                if isinstance(target, ast.Name) and target.id == "model_config":
                    parsed_class.model_config.update(_parse_config_assign(item))

        elif isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name) and item.target.id == "model_config" and isinstance(item.value, ast.Call):
                parsed_class.model_config.update(_parse_config_assign(ast.Assign(targets=[item.target], value=item.value)))
                continue

            relationship = _parse_relationship(item)
            if relationship:
                parsed_class.relationships.append(relationship)
                continue
            field = _parse_field(item, source_lines)
            if field:
                parsed_class.fields.append(field)

        elif isinstance(item, ast.FunctionDef):
            method, synthetic_field = _parse_method(item)
            parsed_class.methods.append(method)
            for field_name, refs in _method_field_enum_hints(item).items():
                method_enum_hints[field_name].update(refs)
            if synthetic_field is not None:
                parsed_class.fields.append(synthetic_field)

        elif isinstance(item, ast.ClassDef) and item.name == "Config":
            parsed_class.model_config.update(_parse_inner_config(item))

    parsed_class.is_abstract = "ABC" in parsed_class.base_classes or any(method.is_abstract for method in parsed_class.methods)
    parsed_class.stereotypes = _compute_stereotypes(parsed_class)
    for field in parsed_class.fields:
        if field.enum_ref_hint is None:
            refs = method_enum_hints.get(field.name, set())
            if len(refs) == 1:
                field.enum_ref_hint = next(iter(refs))
    return parsed_class


def _resolve_ref_to_symbol_id(
    source_module: ParsedModule,
    ref: str | None,
    candidates: dict[str, list[tuple[ParsedModule, str]]],
) -> str | None:
    if not ref:
        return None

    clean = ref.strip("'\"`")
    if "." in clean:
        domain, simple = clean.rsplit(".", 1)
        for module, symbol_id in candidates.get(simple, []):
            if module.domain_name == domain:
                return symbol_id

    simple_name = clean.rsplit(".", 1)[-1]
    refs = candidates.get(simple_name, [])
    if len(refs) == 1:
        return refs[0][1]

    same_domain = [symbol_id for module, symbol_id in refs if module.domain_name == source_module.domain_name]
    if len(same_domain) == 1:
        return same_domain[0]

    return None


def _ref_from_type_annotation(type_annotation: str) -> str:
    text = type_annotation.strip()
    for prefix in ("ClassVar[", "list[", "set["):
        if text.startswith(prefix) and text.endswith("]"):
            return text[len(prefix):-1]
    if text.startswith("dict[") and text.endswith("]"):
        parts = text[5:-1].split(",", 1)
        if len(parts) == 2:
            return parts[1].strip()
    return text


def _resolve_schema_references(schema: DomainSchema) -> None:
    class_candidates: dict[str, list[tuple[ParsedModule, str]]] = {}
    enum_candidates: dict[str, list[tuple[ParsedModule, str]]] = {}
    class_lookup: dict[str, ParsedClass] = {}

    for module in schema.modules:
        for parsed_class in module.classes:
            class_candidates.setdefault(parsed_class.name, []).append((module, parsed_class.symbol_id))
            class_lookup[parsed_class.symbol_id] = parsed_class
        for parsed_enum in module.enums:
            enum_candidates.setdefault(parsed_enum.name, []).append((module, parsed_enum.symbol_id))

    for module in schema.modules:
        for parsed_class in module.classes:
            parsed_class.base_symbol_ids = [
                symbol_id
                for base in parsed_class.base_classes
                if (symbol_id := _resolve_ref_to_symbol_id(module, base, class_candidates))
            ]

            for field in parsed_class.fields:
                if field.is_classvar:
                    continue
                field.target_symbol_id = _resolve_ref_to_symbol_id(
                    module,
                    _ref_from_type_annotation(field.type_annotation),
                    class_candidates,
                )
                if field.target_symbol_id is None:
                    field.target_symbol_id = _resolve_ref_to_symbol_id(
                        module,
                        field.enum_ref_hint or _ref_from_type_annotation(field.type_annotation),
                        enum_candidates,
                    )

            for relationship in parsed_class.relationships:
                relationship.target_symbol_id = _resolve_ref_to_symbol_id(module, relationship.target_class, class_candidates)
                if relationship.ondelete:
                    continue
                if relationship.target_symbol_id is None:
                    continue
                target_class = class_lookup.get(relationship.target_symbol_id)
                if target_class is None:
                    continue
                matching_ondelete = [
                    field.ondelete
                    for field in parsed_class.fields
                    if field.foreign_key
                    and field.foreign_key.split(".", 1)[0] == (target_class.tablename or "")
                    and field.ondelete
                ]
                if matching_ondelete:
                    relationship.ondelete = matching_ondelete[0]


def _iter_model_files(directory: Path, watch_patterns: tuple[str, ...]) -> list[Path]:
    files: set[Path] = set()
    for pattern in watch_patterns:
        files.update(directory.rglob(pattern))
    return sorted(file_path for file_path in files if file_path.name != "__init__.py")


# ── 공개 API ─────────────────────────────────────────────────


def _infer_enum_hints_from_source_comments(
    module: ParsedModule, source_lines: tuple[str, ...], class_nodes: list[ast.ClassDef]
) -> None:
    """필드 주석의 콤마 구분 값 목록을 Enum 멤버값과 비교해 enum_ref_hint 자동 추론.

    예) status: str = Field(...)  # pending, confirmed, completed
    → 같은 모듈에 members={PENDING,CONFIRMED,...}인 Enum이 있으면 자동 연결.
    """
    if not module.enums:
        return

    enum_value_map: dict[str, set[str]] = {
        enum.name: {m.lower() for m in enum.members}
        for enum in module.enums
        if enum.members
    }
    if not enum_value_map:
        return

    # 클래스 필드의 (라인번호 → ParsedField) 매핑 구성
    field_by_line: dict[int, "ParsedField"] = {}
    for cls in module.classes:
        for field in cls.fields:
            if field.enum_ref_hint is not None:
                continue
            if field.type_annotation not in ("str", "str | None"):
                continue
            if hasattr(field, "_source_line"):
                field_by_line[field._source_line] = field

    # AnnAssign 노드에서 라인번호 → 주석 값 목록 추출
    for cls_node in class_nodes:
        for item in ast.walk(cls_node):
            if not isinstance(item, ast.AnnAssign):
                continue
            if not isinstance(item.target, ast.Name):
                continue

            # 멀티라인 Field()의 마지막 줄 주석도 수집
            start = getattr(item, "lineno", 0)
            end = getattr(item, "end_lineno", start)
            comment_values: set[str] = set()
            for lineno in range(start, end + 1):
                if lineno < 1 or lineno > len(source_lines):
                    continue
                line = source_lines[lineno - 1]
                if "#" not in line:
                    continue
                comment = line.split("#", 1)[1].strip()
                # "value1, value2, ..." 형태인 경우만 처리
                parts = [p.strip().lower() for p in comment.split(",") if p.strip()]
                if len(parts) >= 2 and all(re.fullmatch(r"[a-z_][a-z0-9_]*", p) for p in parts):
                    comment_values.update(parts)

            if not comment_values:
                continue

            # 매칭되는 Enum 찾기
            matched = [
                name for name, values in enum_value_map.items()
                if comment_values <= values  # 주석 값이 Enum 멤버의 부분집합
            ]
            if len(matched) != 1:
                continue

            # 해당 필드에 enum_ref_hint 설정
            field_name = item.target.id
            for cls in module.classes:
                for field in cls.fields:
                    if field.name == field_name and field.enum_ref_hint is None:
                        if field.type_annotation in ("str", "str | None"):
                            field.enum_ref_hint = matched[0]


def parse_file(file_path: Path) -> ParsedModule:
    """단일 모델 파일 파싱."""

    file_path = Path(file_path)
    source = file_path.read_text(encoding="utf-8")
    source_lines = tuple(source.splitlines())
    tree = ast.parse(source, filename=str(file_path))
    module = ParsedModule(
        domain_name=_extract_domain_name(file_path),
        file_path=file_path.resolve(),
    )

    class_nodes: list[ast.ClassDef] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if _is_enum_class(node):
                module.enums.append(_parse_enum(node, file_path))
            else:
                class_nodes.append(node)
                module.classes.append(_parse_class(node, file_path, source_lines))

    _infer_enum_hints_from_source_comments(module, source_lines, class_nodes)
    _resolve_schema_references(DomainSchema(modules=[module]))
    return module


def parse_directory(
    watch_dirs: list[str | Path],
    base_path: Path | None = None,
    watch_patterns: list[str] | tuple[str, ...] | None = None,
    watch_class_bases: list[str] | tuple[str, ...] | None = None,
) -> DomainSchema:
    """여러 디렉터리에서 모델 파일을 찾아 파싱.

    watch_class_bases가 지정되면 파일명 패턴 대신 클래스 상속 기반으로 필터링합니다.
    모든 .py 파일을 스캔하되, 지정된 base class를 상속하는 클래스가 하나라도 있는
    파일만 포함합니다. 해당 파일의 Enum도 함께 포함됩니다.
    """

    schema = DomainSchema()

    if watch_class_bases is not None:
        base_set = set(watch_class_bases)
        patterns = ("*.py",)
    else:
        base_set = None
        patterns = tuple(watch_patterns or DEFAULT_WATCH_PATTERNS)

    for dir_path in watch_dirs:
        directory = Path(dir_path)
        if base_path and not directory.is_absolute():
            directory = base_path / directory
        if not directory.exists():
            continue
        for model_file in _iter_model_files(directory, patterns):
            module = parse_file(model_file)
            if base_set is not None:
                module.classes = [
                    cls for cls in module.classes
                    if cls.is_table or any(base in base_set for base in cls.base_classes)
                ]
                if not module.classes:
                    continue
            schema.modules.append(module)

    _resolve_schema_references(schema)
    return schema
