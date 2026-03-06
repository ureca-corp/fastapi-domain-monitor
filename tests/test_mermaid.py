"""Mermaid classDiagram 생성기 테스트."""
from pathlib import Path

from fastapi_domain_monitor.mermaid import generate_mermaid
from fastapi_domain_monitor.models import (
    DomainSchema,
    ParsedClass,
    ParsedEnum,
    ParsedField,
    ParsedModule,
    ParsedRelationship,
)


def _module(domain: str = "test", classes=None, enums=None) -> ParsedModule:
    return ParsedModule(
        domain_name=domain,
        file_path=Path(f"{domain}/_models.py"),
        classes=classes or [],
        enums=enums or [],
    )


def _entity(name: str, fields=None, relationships=None, base_classes=None, is_join=False) -> ParsedClass:
    if is_join:
        bases = base_classes or ["SQLModel"]
    else:
        bases = base_classes or ["BaseModel", "SQLModel"]
    return ParsedClass(
        name=name,
        base_classes=bases,
        is_table=True,
        fields=fields or [],
        relationships=relationships or [],
    )


def test_empty_schema():
    schema = DomainSchema(modules=[])
    result = generate_mermaid(schema)
    assert result == "classDiagram\n"


def test_single_class_entity():
    cls = _entity("Account", fields=[
        ParsedField(name="login_id", type_annotation="str"),
    ])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema)

    assert "namespace students {" in result
    assert "<<Entity>>" in result
    assert "class Account {" in result
    assert "+str login_id" in result


def test_join_table_stereotype():
    cls = _entity("StudentClass", is_join=True, fields=[
        ParsedField(name="student_id", type_annotation="UUID"),
        ParsedField(name="class_id", type_annotation="UUID"),
    ])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema)

    assert "<<JoinTable>>" in result
    assert "<<Entity>>" not in result


def test_enum_rendered_outside_namespace():
    enum = ParsedEnum(name="ActiveStatus", base_class="StrEnum", members=["ACTIVE", "INACTIVE"])
    cls = _entity("Account")
    schema = DomainSchema(modules=[_module("students", classes=[cls], enums=[enum])])
    result = generate_mermaid(schema)

    lines = result.split("\n")
    # Enum은 namespace 닫힌 이후에 등장
    namespace_close_idx = next(i for i, l in enumerate(lines) if l.strip() == "}")
    enum_idx = next(i for i, l in enumerate(lines) if "<<Enumeration>>" in l)
    assert enum_idx > namespace_close_idx
    assert "ACTIVE" in result
    assert "INACTIVE" in result


def test_one_to_one_relationship():
    rel = ParsedRelationship(
        field_name="teacher",
        target_class="Teacher",
        uselist_false=True,
        is_list=False,
    )
    cls = _entity("Account", relationships=[rel])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema)

    assert '"0..1"' in result
    assert '"1"' in result
    assert ": teacher" in result


def test_one_to_many_relationship():
    rel = ParsedRelationship(
        field_name="students",
        target_class="Student",
        is_list=True,
    )
    cls = _entity("Class", relationships=[rel])
    schema = DomainSchema(modules=[_module("classes", classes=[cls])])
    result = generate_mermaid(schema)

    assert '"1"' in result
    assert '"*"' in result
    assert ": students" in result


def test_many_to_many_relationship():
    rel = ParsedRelationship(
        field_name="classes",
        target_class="Class",
        is_list=True,
        link_model="StudentClass",
    )
    cls = _entity("Student", relationships=[rel])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema)

    # 양쪽 모두 "*"
    line = [l for l in result.split("\n") if "classes" in l and "-->" in l][0]
    assert '"*"' in line
    assert line.count('"*"') == 2


def test_duplicate_relationship_deduplicated():
    rel_a = ParsedRelationship(field_name="teacher", target_class="Teacher", uselist_false=True)
    rel_b = ParsedRelationship(field_name="account", target_class="Account", uselist_false=True)
    cls_a = _entity("Account", relationships=[rel_a])
    cls_b = _entity("Teacher", relationships=[rel_b])
    schema = DomainSchema(modules=[_module("users", classes=[cls_a, cls_b])])
    result = generate_mermaid(schema)

    rel_lines = [l for l in result.split("\n") if "-->" in l]
    assert len(rel_lines) == 1


def test_base_fields_hidden_by_default():
    cls = _entity("Account", fields=[
        ParsedField(name="id", type_annotation="UUID", is_primary_key=True),
        ParsedField(name="created_at", type_annotation="datetime"),
        ParsedField(name="login_id", type_annotation="str"),
    ])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema)

    assert "+str login_id" in result
    assert "id" not in result.split("class Account {")[1].split("}")[0] or "+UUID id" not in result
    # 더 직접적 체크
    class_block = result.split("class Account {")[1].split("}")[0]
    assert "+UUID id" not in class_block
    assert "created_at" not in class_block


def test_base_fields_shown():
    cls = _entity("Account", fields=[
        ParsedField(name="id", type_annotation="UUID", is_primary_key=True),
        ParsedField(name="login_id", type_annotation="str"),
    ])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema, show_base_fields=True)

    assert "+UUID id" in result
    assert "+str login_id" in result


def test_nullable_field_has_question_mark():
    cls = _entity("Account", fields=[
        ParsedField(name="contact", type_annotation="str | None", is_nullable=True),
    ])
    schema = DomainSchema(modules=[_module("students", classes=[cls])])
    result = generate_mermaid(schema)

    assert "+str? contact" in result


def test_fk_inferred_relationship():
    """FK만 있고 Relationship() 없는 경우 → 관계선 자동 생성."""
    from fastapi_domain_monitor.models import ParsedClass

    student = _entity("Student", fields=[
        ParsedField(name="account_id", type_annotation="UUID", foreign_key="accounts.id"),
    ])
    account = ParsedClass(
        name="Account",
        base_classes=["BaseModel", "SQLModel"],
        is_table=True,
        tablename="accounts",
        fields=[ParsedField(name="login_id", type_annotation="str")],
        relationships=[],
    )
    schema = DomainSchema(modules=[
        _module("students", classes=[student]),
        _module("accounts", classes=[account]),
    ])
    result = generate_mermaid(schema)

    rel_lines = [l for l in result.split("\n") if "-->" in l]
    assert len(rel_lines) == 1
    assert "Student" in rel_lines[0]
    assert "Account" in rel_lines[0]
    assert "account_id" in rel_lines[0]


def test_enum_relationship():
    """필드 타입이 Enum이면 점선 연결선(..>) 생성."""
    enum = ParsedEnum(name="ActiveStatus", base_class="StrEnum", members=["ACTIVE", "INACTIVE"])
    cls = _entity("Account", fields=[
        ParsedField(name="status", type_annotation="ActiveStatus"),
    ])
    schema = DomainSchema(modules=[_module("accounts", classes=[cls], enums=[enum])])
    result = generate_mermaid(schema)

    assert "..>" in result
    assert "ActiveStatus" in result
    assert ": status" in result


def test_fk_no_duplicate_with_explicit():
    """Relationship()과 FK가 동시에 있으면 관계선 1개만 생성."""
    from fastapi_domain_monitor.models import ParsedClass

    rel = ParsedRelationship(field_name="account", target_class="Account", is_list=False)
    student = _entity("Student",
        fields=[ParsedField(name="account_id", type_annotation="UUID", foreign_key="accounts.id")],
        relationships=[rel],
    )
    account = ParsedClass(
        name="Account",
        base_classes=["BaseModel", "SQLModel"],
        is_table=True,
        tablename="accounts",
        fields=[],
        relationships=[],
    )
    schema = DomainSchema(modules=[
        _module("students", classes=[student]),
        _module("accounts", classes=[account]),
    ])
    result = generate_mermaid(schema)

    rel_lines = [l for l in result.split("\n") if "-->" in l]
    assert len(rel_lines) == 1
