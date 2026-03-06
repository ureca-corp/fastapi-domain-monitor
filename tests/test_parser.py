"""parser.py 단위 테스트."""
from pathlib import Path

import pytest

from fastapi_domain_monitor.parser import DEFAULT_WATCH_PATTERNS, parse_directory, parse_file

SAMPLE_PATH = Path(__file__).parent / "fixtures" / "sample_models.py"
QUALIFIED_PATH = Path(__file__).parent / "fixtures" / "sample_models_qualified.py"


@pytest.fixture(scope="module")
def parsed_sample():
    return parse_file(SAMPLE_PATH)


@pytest.fixture(scope="module")
def parsed_qualified():
    return parse_file(QUALIFIED_PATH)


def _find_class(parsed, name):
    return next(item for item in parsed.classes if item.name == name)


def _find_field(parsed_class, name):
    return next(item for item in parsed_class.fields if item.name == name)


def _find_method(parsed_class, name):
    return next(item for item in parsed_class.methods if item.name == name)


def _find_relationship(parsed_class, name):
    return next(item for item in parsed_class.relationships if item.field_name == name)


def _parse_source(tmp_path, source: str, name: str = "tmp_models.py"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return parse_file(path)


def test_parse_enums(parsed_sample):
    names = {enum.name for enum in parsed_sample.enums}
    assert names == {"ActiveStatus", "AccountRole", "GradingStatus"}
    assert all(enum.base_class == "StrEnum" for enum in parsed_sample.enums)


def test_parse_join_table(parsed_sample):
    join_table = _find_class(parsed_sample, "StudentClass")
    assert join_table.is_join_table is True
    assert join_table.stereotypes == ["JoinTable"]
    assert join_table.tablename == "student_classes"


def test_parse_basic_field_metadata(parsed_sample):
    account = _find_class(parsed_sample, "Account")
    login_id = _find_field(account, "login_id")
    assert login_id.type_annotation == "str"
    assert login_id.constraints["max_length"] == "50"
    assert login_id.constraints["unique"] == "True"

    active_status = _find_field(account, "active_status")
    assert active_status.has_default is True
    assert active_status.default_repr == "ActiveStatus.ACTIVE"
    assert active_status.target_symbol_id is not None

    primary_key = _find_field(account, "id")
    assert primary_key.is_primary_key is True

    exam = _find_class(parsed_sample, "Exam")
    lifecycle_status = _find_field(exam, "lifecycle_status")
    assert lifecycle_status.enum_ref_hint == "GradingStatus"
    assert lifecycle_status.target_symbol_id is not None


def test_parse_relationship_metadata(parsed_sample):
    student = _find_class(parsed_sample, "Student")
    classes_rel = _find_relationship(student, "classes")
    assert classes_rel.is_list is True
    assert classes_rel.link_model == "StudentClass"
    assert classes_rel.target_symbol_id is not None

    account = _find_class(parsed_sample, "Account")
    teacher_rel = _find_relationship(account, "teacher")
    assert teacher_rel.uselist_false is True
    assert teacher_rel.back_populates == "account"


def test_parse_source_span_and_symbol_id(parsed_sample):
    account = _find_class(parsed_sample, "Account")
    assert len(account.symbol_id) == 16
    assert account.source_span.file_path == SAMPLE_PATH.resolve()
    assert account.source_span.start_line < account.source_span.end_line


def test_parse_qualified_patterns(parsed_qualified):
    order = _find_class(parsed_qualified, "Order")
    note = _find_field(order, "note")
    tags = _find_field(order, "tags")
    items = _find_relationship(order, "items")
    payload = _find_field(_find_class(parsed_qualified, "Report"), "payload")

    assert note.is_nullable is True
    assert tags.collection_kind == "list"
    assert items.target_symbol_id is not None
    assert payload.is_json is True


def test_parse_methods_config_and_special_fields(tmp_path):
    parsed = _parse_source(
        tmp_path,
        """
from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field, field_serializer, field_validator


class TaxLine(BaseModel):
    rate: int


class Invoice(BaseModel, ABC):
    \"\"\"Invoice DTO summary.

    More detail that should not matter to the compact view.
    \"\"\"
    model_config = ConfigDict(title="Invoice", extra="forbid", frozen=True)

    kind: ClassVar[str] = "invoice"
    _secret: str = PrivateAttr(default="x")
    amount: Annotated[int, Field(alias="total_amount", gt=0)]
    taxes: list[TaxLine]

    @computed_field
    @property
    def total(self) -> int:
        return self.amount

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: int) -> int:
        return value

    @field_serializer("taxes")
    def serialize_taxes(self, value) -> str:
        return "ok"

    @abstractmethod
    def charge(self) -> None:
        raise NotImplementedError
""",
    )

    invoice = _find_class(parsed, "Invoice")
    assert invoice.is_abstract is True
    assert invoice.stereotypes == ["DTO", "Abstract"]
    assert invoice.model_config["extra"] == "forbid"
    assert invoice.model_config["frozen"] == "True"

    amount = _find_field(invoice, "amount")
    assert amount.alias == "total_amount"
    assert amount.constraints["gt"] == "0"

    kind = _find_field(invoice, "kind")
    assert kind.is_classvar is True

    secret = _find_field(invoice, "_secret")
    assert secret.is_private is True
    assert secret.default_repr == "'x'"

    taxes = _find_field(invoice, "taxes")
    assert taxes.target_symbol_id == _find_class(parsed, "TaxLine").symbol_id

    total = _find_field(invoice, "total")
    assert total.is_computed is True

    validate_amount = _find_method(invoice, "validate_amount")
    assert validate_amount.is_classmethod is True
    assert validate_amount.is_validator is True

    serialize_taxes = _find_method(invoice, "serialize_taxes")
    assert serialize_taxes.is_serializer is True

    charge = _find_method(invoice, "charge")
    assert charge.is_abstract is True


def test_parse_method_body_enum_usage_as_field_hint(tmp_path):
    parsed = _parse_source(
        tmp_path,
        """
from enum import StrEnum


class AccountRole(StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class Account:
    role: str

    @property
    def is_teacher(self) -> bool:
        return self.role == AccountRole.TEACHER
""",
    )

    account = _find_class(parsed, "Account")
    role = _find_field(account, "role")
    enum_symbol = next(item.symbol_id for item in parsed.enums if item.name == "AccountRole")

    assert role.enum_ref_hint == "AccountRole"
    assert role.target_symbol_id == enum_symbol


def test_parse_field_comment_enum_hint(tmp_path):
    parsed = _parse_source(
        tmp_path,
        """
from enum import StrEnum


class SectionType(StrEnum):
    ESSAY = "essay"


class AlimtalkSendStatus(StrEnum):
    SENT = "sent"


class Section:
    section_type: str  # SectionType


class AlimtalkSendResult:
    status: str  # AlimtalkSendStatus
    message_type: str | None = None  # alimtalk / sms
""",
    )

    section = _find_class(parsed, "Section")
    result = _find_class(parsed, "AlimtalkSendResult")

    section_type = _find_field(section, "section_type")
    status = _find_field(result, "status")
    message_type = _find_field(result, "message_type")

    assert section_type.enum_ref_hint == "SectionType"
    assert section_type.target_symbol_id == next(item.symbol_id for item in parsed.enums if item.name == "SectionType")
    assert status.enum_ref_hint == "AlimtalkSendStatus"
    assert status.target_symbol_id == next(item.symbol_id for item in parsed.enums if item.name == "AlimtalkSendStatus")
    assert message_type.enum_ref_hint is None
    assert message_type.target_symbol_id is None


def test_parse_directory_uses_extended_patterns(tmp_path):
    accounts_dir = tmp_path / "accounts"
    billing_dir = tmp_path / "billing"
    misc_dir = tmp_path / "misc"
    accounts_dir.mkdir()
    billing_dir.mkdir()
    misc_dir.mkdir()

    (accounts_dir / "schemas.py").write_text("class AccountSchema:\n    id: int\n", encoding="utf-8")
    (billing_dir / "dto.py").write_text("class InvoiceDTO:\n    total: int\n", encoding="utf-8")
    (misc_dir / "helpers.py").write_text("class Helper:\n    pass\n", encoding="utf-8")

    schema = parse_directory([tmp_path], watch_patterns=list(DEFAULT_WATCH_PATTERNS))
    classes = {parsed_class.name for parsed_class in schema.all_classes()}

    assert classes == {"AccountSchema", "InvoiceDTO"}


def test_field_nullable_and_defaults_from_field_call(tmp_path):
    parsed = _parse_source(
        tmp_path,
        """
from sqlmodel import Field, SQLModel
from uuid import UUID


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: UUID | None = Field(None, primary_key=True)
    manager_id: UUID = Field(sa_column_kwargs={"nullable": True})
""",
    )

    user = _find_class(parsed, "User")
    identifier = _find_field(user, "id")
    manager_id = _find_field(user, "manager_id")

    assert identifier.has_default is True
    assert identifier.default_repr == "None"
    assert manager_id.is_nullable is True
