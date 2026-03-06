"""Mermaid classDiagram 생성기 테스트."""
from pathlib import Path

import pytest

from fastapi_domain_monitor.mermaid import generate_mermaid
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


def _span(start: int = 1, end: int = 10) -> SourceSpan:
    return SourceSpan(file_path=Path("/tmp/models.py"), start_line=start, end_line=end)


def _module(domain: str = "test", classes=None, enums=None) -> ParsedModule:
    return ParsedModule(
        domain_name=domain,
        file_path=Path(f"/tmp/{domain}/models.py"),
        classes=classes or [],
        enums=enums or [],
    )


def _class(
    name: str,
    *,
    symbol_id: str,
    base_classes=None,
    base_symbol_ids=None,
    fields=None,
    relationships=None,
    methods=None,
    stereotypes=None,
    is_table: bool = False,
    is_protocol_like: bool = False,
    is_abstract: bool = False,
    docstring: str | None = None,
    model_config=None,
    tablename: str | None = None,
) -> ParsedClass:
    return ParsedClass(
        name=name,
        symbol_id=symbol_id,
        source_span=_span(),
        base_classes=base_classes or [],
        base_symbol_ids=base_symbol_ids or [],
        fields=fields or [],
        relationships=relationships or [],
        methods=methods or [],
        stereotypes=stereotypes or [],
        is_table=is_table,
        is_protocol_like=is_protocol_like,
        is_abstract=is_abstract,
        docstring=docstring,
        model_config=model_config or {},
        tablename=tablename,
    )


def _enum(name: str, symbol_id: str) -> ParsedEnum:
    return ParsedEnum(
        name=name,
        symbol_id=symbol_id,
        source_span=_span(),
        base_class="StrEnum",
        members=["ACTIVE", "INACTIVE"],
    )


def test_empty_schema():
    assert generate_mermaid(DomainSchema()) == "classDiagram\n"


def test_compact_render_includes_methods_and_stereotypes():
    account = _class(
        "Account",
        symbol_id="account1",
        fields=[
            ParsedField(name="id", type_annotation="UUID", is_primary_key=True),
            ParsedField(name="email", type_annotation="str", default_repr="'demo@example.com'"),
            ParsedField(name="slug", type_annotation="str", default_factory="build_slug"),
            ParsedField(name="_secret", type_annotation="str", visibility="private", is_private=True),
            ParsedField(name="kind", type_annotation="ClassVar[str]", visibility="public", is_classvar=True),
            ParsedField(name="total", type_annotation="int", is_computed=True),
        ],
        methods=[
            ParsedMethod(name="login", return_type="bool"),
            ParsedMethod(name="_normalize", visibility="private"),
        ],
        stereotypes=["Entity"],
        is_table=True,
    )
    result = generate_mermaid(DomainSchema(modules=[_module("accounts", classes=[account])]))

    assert 'class node_account1["Account"] {' in result
    assert "<<Entity>>" in result
    assert "+str email = 'demo@example.com'" in result
    assert "+str slug = build_slug()" in result
    assert "+login() bool" in result
    assert "_secret" not in result
    assert "ClassVar" not in result
    assert "total" not in result
    assert "_normalize" not in result


def test_unsupported_detail_level_raises_value_error():
    invoice = _class("Invoice", symbol_id="invoice1")

    with pytest.raises(ValueError, match="Unsupported detail level"):
        generate_mermaid(
            DomainSchema(modules=[_module("billing", classes=[invoice])]),
            detail_level="full",
        )


def test_inheritance_realization_and_framework_base_filter():
    protocol = _class("Repository", symbol_id="repo1", is_protocol_like=True, stereotypes=["ValueObject"])
    base = _class("BaseEntity", symbol_id="base1", stereotypes=["Abstract"], is_abstract=True)
    framework = _class("BaseModel", symbol_id="framework1")
    user_repo = _class(
        "UserRepository",
        symbol_id="userrepo1",
        base_classes=["Repository"],
        base_symbol_ids=["repo1"],
    )
    account = _class(
        "Account",
        symbol_id="account2",
        base_classes=["BaseEntity", "BaseModel"],
        base_symbol_ids=["base1", "framework1"],
    )
    result = generate_mermaid(DomainSchema(modules=[_module("core", classes=[protocol, base, framework, user_repo, account])]))

    assert "node_userrepo1 ..|> node_repo1" in result
    assert "node_base1 <|-- node_account2" in result
    assert "node_framework1 <|-- node_account2" not in result


def test_relationships_and_composition_render():
    status = _enum("Status", "enum1")
    address = _class("Address", symbol_id="address1", stereotypes=["ValueObject"])
    user = _class(
        "User",
        symbol_id="user1",
        fields=[
            ParsedField(name="status", type_annotation="Status", target_symbol_id="enum1"),
            ParsedField(name="address", type_annotation="Address", target_symbol_id="address1"),
            ParsedField(name="emails", type_annotation="list[Email]", collection_kind="list", target_symbol_id="email1"),
        ],
        relationships=[
            ParsedRelationship(field_name="profile", target_class="Profile", target_symbol_id="profile1", back_populates="user"),
            ParsedRelationship(field_name="orders", target_class="Order", target_symbol_id="order1", is_list=True, cascade_delete=True),
        ],
    )
    profile = _class(
        "Profile",
        symbol_id="profile1",
        relationships=[ParsedRelationship(field_name="user", target_class="User", target_symbol_id="user1", back_populates="profile")],
    )
    order = _class("Order", symbol_id="order1")
    email = _class("Email", symbol_id="email1")

    schema = DomainSchema(modules=[_module("accounts", classes=[user, profile, order, address, email], enums=[status])])
    result = generate_mermaid(schema)

    assert "node_user1 ..> node_enum1 : status" in result
    assert 'node_user1 "1" *-- "1" node_address1 : address' in result
    assert 'node_user1 "1" *-- "*" node_email1 : emails' in result
    assert 'node_user1 "1" --> "1" node_profile1 : profile' in result
    assert 'node_user1 "1" *-- "*" node_order1 : orders' in result


def test_fk_inference_and_domain_filter():
    user = _class("User", symbol_id="user2", tablename="users")
    report = _class(
        "Report",
        symbol_id="report1",
        fields=[ParsedField(name="reviewer_id", type_annotation="UUID", foreign_key="users.id")],
    )
    schema = DomainSchema(modules=[_module("accounts", classes=[user]), _module("reports", classes=[report])])

    all_result = generate_mermaid(schema)
    filtered_result = generate_mermaid(schema, visible_domains={"reports"})

    assert 'node_report1 "1" --> "1" node_user2 : reviewer_id' in all_result
    assert 'node_report1 "1" --> "1" node_user2 : reviewer_id' not in filtered_result


def test_duplicate_names_render_with_distinct_aliases():
    admin_user = _class("User", symbol_id="user_admin")
    account_user = _class("User", symbol_id="user_account")
    result = generate_mermaid(
        DomainSchema(modules=[_module("admin", classes=[admin_user]), _module("accounts", classes=[account_user])])
    )

    assert 'class node_user_admin["User"] {' in result
    assert 'class node_user_account["User"] {' in result
