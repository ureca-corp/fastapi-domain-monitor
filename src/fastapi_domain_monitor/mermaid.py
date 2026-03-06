"""DomainSchema → Mermaid classDiagram 텍스트 변환기."""
from __future__ import annotations

from collections import defaultdict

from .models import DomainSchema, ParsedClass, ParsedEnum, ParsedField, ParsedMethod, ParsedRelationship

BASE_FIELDS = {"id", "created_at", "updated_at", "deleted_at"}
FRAMEWORK_BASES = {"BaseModel", "SQLModel", "object"}
DETAIL_LEVELS = {"compact"}


def generate_mermaid(
    schema: DomainSchema,
    show_base_fields: bool = False,
    detail_level: str = "compact",
    visible_domains: set[str] | None = None,
    visible_stereotypes: set[str] | None = None,
) -> str:
    """DomainSchema를 Mermaid classDiagram 텍스트로 변환."""

    if detail_level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {detail_level}")

    filtered_modules = [
        module for module in schema.modules
        if visible_domains is None or module.domain_name in visible_domains
    ]
    if not filtered_modules:
        return "classDiagram\n"

    class_lookup = {parsed_class.symbol_id: parsed_class for parsed_class in schema.all_classes()}
    enum_lookup = {parsed_enum.symbol_id: parsed_enum for parsed_enum in schema.all_enums()}
    alias_by_symbol_id = {
        symbol.symbol_id: _diagram_id(symbol.symbol_id)
        for symbol in schema.all_symbols()
    }
    visible_class_ids = {
        parsed_class.symbol_id
        for module in filtered_modules
        for parsed_class in module.classes
        if _matches_stereotypes(parsed_class.stereotypes, visible_stereotypes)
    }
    visible_enum_ids = {
        parsed_enum.symbol_id
        for module in filtered_modules
        for parsed_enum in module.enums
        if visible_stereotypes is None or "Enumeration" in visible_stereotypes
    }
    tablename_lookup = {
        parsed_class.tablename: parsed_class.symbol_id
        for parsed_class in schema.all_classes()
        if parsed_class.tablename
    }

    lines = ["classDiagram", "direction LR"]

    for module in filtered_modules:
        visible_module_classes = [c for c in module.classes if c.symbol_id in visible_class_ids]
        visible_module_enums = [e for e in module.enums if e.symbol_id in visible_enum_ids]
        if not visible_module_classes and not visible_module_enums:
            continue
        lines.append(f"namespace {module.domain_name} {{")
        for parsed_class in visible_module_classes:
            _render_class(
                parsed_class,
                lines,
                alias_by_symbol_id[parsed_class.symbol_id],
                show_base_fields=show_base_fields,
            )
        for parsed_enum in visible_module_enums:
            _render_enum(parsed_enum, lines, alias_by_symbol_id[parsed_enum.symbol_id])
        lines.append("}")

    relation_lines: list[str] = []
    click_lines: list[str] = []
    seen_relationships: set[tuple[str, str, str, str]] = set()

    for module in filtered_modules:
        for parsed_class in module.classes:
            source_alias = alias_by_symbol_id[parsed_class.symbol_id]

            for base_symbol_id in parsed_class.base_symbol_ids:
                if base_symbol_id not in visible_class_ids:
                    continue
                base_class = class_lookup[base_symbol_id]
                if base_class.name in FRAMEWORK_BASES:
                    continue
                base_alias = alias_by_symbol_id[base_symbol_id]
                if base_class.is_protocol_like:
                    relation_lines.append(f"{source_alias} ..|> {base_alias}")
                else:
                    relation_lines.append(f"{base_alias} <|-- {source_alias}")

            for relationship in parsed_class.relationships:
                if relationship.target_symbol_id not in visible_class_ids:
                    continue
                target_alias = alias_by_symbol_id[relationship.target_symbol_id]
                if relationship.back_populates:
                    key = tuple(sorted((
                        f"{parsed_class.symbol_id}:{relationship.field_name}",
                        f"{relationship.target_symbol_id}:{relationship.back_populates}",
                    )))
                else:
                    key = (
                        parsed_class.symbol_id,
                        relationship.target_symbol_id,
                        relationship.field_name,
                        relationship.back_populates or "",
                    )
                if key in seen_relationships:
                    continue
                seen_relationships.add(key)
                relation_lines.append(_render_relationship(source_alias, target_alias, relationship))

            for field in parsed_class.fields:
                if not field.foreign_key:
                    continue
                target_symbol_id = tablename_lookup.get(field.foreign_key.split(".", 1)[0])
                if target_symbol_id not in visible_class_ids:
                    continue
                if any(
                    relationship.target_symbol_id == target_symbol_id and field.name == f"{relationship.field_name}_id"
                    for relationship in parsed_class.relationships
                ):
                    continue
                target_alias = alias_by_symbol_id[target_symbol_id]
                relation_lines.append(f'{source_alias} "1" --> "1" {target_alias} : {field.name}')

            for field in parsed_class.fields:
                if field.is_classvar:
                    continue
                if field.target_symbol_id in visible_enum_ids:
                    enum_alias = alias_by_symbol_id[field.target_symbol_id]
                    relation_lines.append(f"{source_alias} ..> {enum_alias} : {field.name}")
                    continue
                if field.target_symbol_id not in visible_class_ids:
                    continue
                if field.is_private:
                    continue
                if field.is_computed:
                    continue
                if any(relationship.field_name == field.name for relationship in parsed_class.relationships):
                    continue
                target_alias = alias_by_symbol_id[field.target_symbol_id]
                relation_lines.append(_render_composition(source_alias, target_alias, field))

            click_lines.append(f'click {source_alias} call handleSymbolClick() "Open source"')

        for parsed_enum in module.enums:
            enum_alias = alias_by_symbol_id[parsed_enum.symbol_id]
            click_lines.append(f'click {enum_alias} call handleSymbolClick() "Open source"')

    relation_lines = _dedupe_preserve_order(relation_lines)
    click_lines = _dedupe_preserve_order(click_lines)

    lines.extend(relation_lines)
    lines.extend(click_lines)
    return "\n".join(lines) + "\n"


def _dedupe_preserve_order(lines: list[str]) -> list[str]:
    return list(dict.fromkeys(lines))


def _diagram_id(symbol_id: str) -> str:
    return f"node_{symbol_id}"


def _render_class(
    parsed_class: ParsedClass,
    lines: list[str],
    diagram_id: str,
    *,
    show_base_fields: bool,
) -> None:
    lines.append(f'    class {diagram_id}["{parsed_class.name}"] {{')
    for stereotype in parsed_class.stereotypes:
        lines.append(f"        <<{stereotype}>>")

    for field in _visible_fields(parsed_class.fields, show_base_fields):
        lines.append(f"        {_format_field(field)}")

    for method in _visible_methods(parsed_class.methods):
        lines.append(f"        {_format_method(method)}")

    lines.append("    }")


def _render_enum(parsed_enum: ParsedEnum, lines: list[str], diagram_id: str) -> None:
    lines.append(f'    class {diagram_id}["{parsed_enum.name}"] {{')
    lines.append("        <<Enumeration>>")
    for member in parsed_enum.members:
        lines.append(f"        {member}")
    lines.append("    }")


def _visible_fields(
    fields: list[ParsedField],
    show_base_fields: bool,
) -> list[ParsedField]:
    visible = []
    for field in fields:
        if not show_base_fields and field.name in BASE_FIELDS:
            continue
        if field.is_private or field.is_classvar or field.is_computed:
            continue
        visible.append(field)
    return sorted(visible, key=lambda field: (not field.is_primary_key, field.is_private, field.name))


def _visible_methods(methods: list[ParsedMethod]) -> list[ParsedMethod]:
    return [method for method in methods if method.visibility == "public"]


def _format_field(field: ParsedField) -> str:
    prefix = "+" if field.visibility == "public" else "-"
    type_label = "JSON" if field.is_json else field.type_annotation
    nullable = "?" if field.is_nullable else ""
    classifier = "$" if field.is_classvar else ""
    return f"{prefix}{type_label}{nullable} {field.name}{classifier}"


def _format_field_default(field: ParsedField) -> str:
    if field.default_repr is not None:
        return f" = {field.default_repr}"
    if field.default_factory:
        return f" = {field.default_factory}()"
    return ""


def _format_method(method: ParsedMethod) -> str:
    prefix = "+" if method.visibility == "public" else "-"
    params = ", ".join(method.parameters)
    return_type = f" {method.return_type}" if method.return_type else ""
    classifier = ""
    if method.is_classmethod or method.is_staticmethod:
        classifier += "$"
    if method.is_abstract:
        classifier += "*"
    return f"{prefix}{method.name}({params}){return_type}{classifier}"


def _render_relationship(source_alias: str, target_alias: str, relationship: ParsedRelationship) -> str:
    arrow = "*--" if relationship.is_composition else "-->"
    if relationship.is_list and relationship.link_model is not None:
        left, right = '"*"', '"*"'
    elif relationship.is_list:
        left, right = '"1"', '"*"'
    elif relationship.uselist_false:
        left, right = '"1"', '"0..1"'
    else:
        left, right = '"1"', '"1"'
    return f"{source_alias} {left} {arrow} {right} {target_alias} : {relationship.field_name}"


def _matches_stereotypes(stereotypes: list[str], visible: set[str] | None) -> bool:
    """visible이 None이면 모두 표시. 클래스에 stereotype이 없으면 'Other'로 취급."""
    if visible is None:
        return True
    if not stereotypes:
        return "Other" in visible
    return bool(set(stereotypes) & visible)


def _render_composition(source_alias: str, target_alias: str, field: ParsedField) -> str:
    if field.collection_kind in {"list", "set", "dict"}:
        right = '"*"'
    elif field.is_nullable:
        right = '"0..1"'
    else:
        right = '"1"'
    return f'{source_alias} "1" *-- {right} {target_alias} : {field.name}'
