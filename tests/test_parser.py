"""parser.py 단위 테스트 — tests/fixtures/sample_models.py 파싱 검증."""
from pathlib import Path

import pytest

from fastapi_domain_monitor.parser import parse_file

SAMPLE_PATH = Path(__file__).parent / "fixtures" / "sample_models.py"


@pytest.fixture(scope="module")
def parsed():
    return parse_file(SAMPLE_PATH)


def _find_class(parsed, name):
    return next(c for c in parsed.classes if c.name == name)


def _find_field(cls, name):
    return next(f for f in cls.fields if f.name == name)


def _find_rel(cls, name):
    return next(r for r in cls.relationships if r.field_name == name)


# ── Enum ──────────────────────────────────────────────────────


def test_parse_enums(parsed):
    names = {e.name for e in parsed.enums}
    assert names == {"ActiveStatus", "AccountRole", "GradingStatus"}
    for e in parsed.enums:
        assert e.base_class == "StrEnum"
        assert len(e.members) >= 2


# ── Join Table ────────────────────────────────────────────────


def test_parse_join_table(parsed):
    sc = _find_class(parsed, "StudentClass")
    assert sc.is_join_table is True
    assert sc.tablename == "student_classes"

    fk_fields = [f for f in sc.fields if f.foreign_key]
    assert len(fk_fields) == 2
    fk_targets = {f.foreign_key for f in fk_fields}
    assert fk_targets == {"students.id", "classes.id"}


# ── 기본 필드 ─────────────────────────────────────────────────


def test_parse_basic_fields(parsed):
    account = _find_class(parsed, "Account")

    login_id = _find_field(account, "login_id")
    assert login_id.type_annotation == "str"
    assert login_id.is_primary_key is False

    pwd = _find_field(account, "password_hash")
    assert pwd.type_annotation == "str"

    active = _find_field(account, "active_status")
    assert active.has_default is True

    pk = _find_field(account, "id")
    assert pk.is_primary_key is True


# ── Relationship: uselist=False ───────────────────────────────


def test_parse_relationship_uselist_false(parsed):
    account = _find_class(parsed, "Account")
    teacher_rel = _find_rel(account, "teacher")
    assert teacher_rel.uselist_false is True
    assert teacher_rel.target_class == "Teacher"
    assert teacher_rel.is_list is False
    assert teacher_rel.back_populates == "account"


# ── Relationship: list + link_model ──────────────────────────


def test_parse_relationship_list_with_link_model(parsed):
    student = _find_class(parsed, "Student")
    classes_rel = _find_rel(student, "classes")
    assert classes_rel.is_list is True
    assert classes_rel.link_model == "StudentClass"
    assert classes_rel.target_class == "Class"
    assert classes_rel.back_populates == "students"


# ── sa_column 필드 ────────────────────────────────────────────


def test_parse_sa_column_field(parsed):
    exam = _find_class(parsed, "Exam")
    lifecycle = _find_field(exam, "lifecycle_status")
    assert lifecycle.is_sa_column is True
    assert lifecycle.is_json is False


# ── JSON 필드 ─────────────────────────────────────────────────


def test_parse_json_field(parsed):
    exam = _find_class(parsed, "Exam")
    scores = _find_field(exam, "scores")
    assert scores.is_json is True
    assert scores.is_sa_column is True


# ── 크로스도메인 FK (foreign_key 없음) ───────────────────────


def test_parse_cross_domain_fk(parsed):
    exam = _find_class(parsed, "Exam")
    teacher_id = _find_field(exam, "teacher_id")
    assert teacher_id.foreign_key is None
    assert teacher_id.type_annotation == "UUID"


# ── nullable 타입 ─────────────────────────────────────────────


def test_parse_nullable_type(parsed):
    student = _find_class(parsed, "Student")
    contact = _find_field(student, "contact")
    assert contact.is_nullable is True
    assert contact.type_annotation == "str"
    assert contact.has_default is True
