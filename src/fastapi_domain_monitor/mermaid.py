"""DomainSchema → Mermaid classDiagram 텍스트 변환기."""
from __future__ import annotations

from .models import DomainSchema, ParsedClass, ParsedEnum, ParsedField, ParsedModule, ParsedRelationship

BASE_FIELDS = {"id", "created_at", "updated_at", "deleted_at"}


def generate_mermaid(schema: DomainSchema, show_base_fields: bool = False) -> str:
    """DomainSchema를 Mermaid classDiagram 텍스트로 변환.

    Args:
        schema: 파싱된 도메인 스키마.
        show_base_fields: id/created_at/updated_at/deleted_at 표시 여부.
    """
    lines: list[str] = ["classDiagram"]

    # 1. namespace 블록 (모듈별)
    for module in schema.modules:
        if not module.classes:
            continue
        lines.append(f"namespace {module.domain_name} {{")
        for cls in module.classes:
            _render_class(cls, lines, show_base_fields, indent=4)
        lines.append("}")

    # 2. Enum은 namespace 밖에 배치
    for enum in schema.all_enums():
        _render_enum(enum, lines)

    # 3. 관계선
    seen: set[frozenset[str]] = set()
    for module in schema.modules:
        for cls in module.classes:
            for rel in cls.relationships:
                pair = frozenset({cls.name, rel.target_class})
                if pair in seen:
                    continue
                seen.add(pair)
                lines.append(_render_relationship(cls.name, rel))

    return "\n".join(lines) + "\n"


def _render_class(cls: ParsedClass, lines: list[str], show_base_fields: bool, indent: int) -> None:
    pad = " " * indent
    lines.append(f"{pad}class {cls.name} {{")

    # 스테레오타입
    if cls.is_join_table:
        lines.append(f"{pad}    <<JoinTable>>")
    elif cls.is_table:
        lines.append(f"{pad}    <<Entity>>")

    # 필드: PK 먼저, 나머지
    pk_fields = [f for f in cls.fields if f.is_primary_key]
    other_fields = [f for f in cls.fields if not f.is_primary_key]

    for f in pk_fields + other_fields:
        if not show_base_fields and f.name in BASE_FIELDS:
            continue
        lines.append(f"{pad}    {_format_field(f)}")

    lines.append(f"{pad}}}")


def _format_field(f: ParsedField) -> str:
    if f.is_json:
        type_str = "JSON"
    else:
        type_str = _clean_type(f.type_annotation)

    nullable = "?" if f.is_nullable else ""
    return f"+{type_str}{nullable} {f.name}"


def _clean_type(annotation: str) -> str:
    """Remove | None and Optional wrapper from type annotations."""
    cleaned = annotation.replace(" | None", "").replace("| None", "")
    if cleaned.startswith("Optional[") and cleaned.endswith("]"):
        cleaned = cleaned[9:-1]
    return cleaned.strip()


def _render_enum(enum: ParsedEnum, lines: list[str]) -> None:
    lines.append(f"class {enum.name} {{")
    lines.append("    <<Enumeration>>")
    for member in enum.members:
        lines.append(f"    {member}")
    lines.append("}")


def _render_relationship(source: str, rel: ParsedRelationship) -> str:
    if rel.is_list and rel.link_model is not None:
        left, right = '"*"', '"*"'
    elif rel.is_list:
        left, right = '"1"', '"*"'
    elif rel.uselist_false:
        left, right = '"1"', '"0..1"'
    else:
        left, right = '"1"', '"1"'

    return f'{source} {left} --> {right} {rel.target_class} : {rel.field_name}'
