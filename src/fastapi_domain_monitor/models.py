"""
중간 표현(IR) - AST 파서와 Mermaid 생성기 사이의 공유 데이터 구조.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SourceSpan:
    """파싱된 심볼의 소스 위치."""

    file_path: Path
    start_line: int
    end_line: int


@dataclass
class ParsedField:
    """클래스의 필드 하나."""

    name: str
    type_annotation: str
    visibility: str = "public"
    is_primary_key: bool = False
    is_nullable: bool = False
    has_default: bool = False
    foreign_key: str | None = None
    ondelete: str | None = None
    is_sa_column: bool = False
    is_json: bool = False
    alias: str | None = None
    default_repr: str | None = None
    default_factory: str | None = None
    constraints: dict[str, str] = field(default_factory=dict)
    is_private: bool = False
    is_classvar: bool = False
    is_computed: bool = False
    collection_kind: str | None = None
    target_symbol_id: str | None = None


@dataclass
class ParsedMethod:
    """클래스 메서드/연산."""

    name: str
    parameters: list[str] = field(default_factory=list)
    return_type: str | None = None
    visibility: str = "public"
    decorator_labels: list[str] = field(default_factory=list)
    is_classmethod: bool = False
    is_staticmethod: bool = False
    is_abstract: bool = False
    is_property: bool = False
    is_computed_field: bool = False
    is_validator: bool = False
    is_serializer: bool = False


@dataclass
class ParsedRelationship:
    """SQLModel Relationship() 필드."""

    field_name: str
    target_class: str
    back_populates: str | None = None
    is_list: bool = False
    collection_kind: str | None = None
    link_model: str | None = None
    uselist_false: bool = False
    cascade_delete: bool = False
    has_delete_orphan: bool = False
    ondelete: str | None = None
    target_symbol_id: str | None = None

    @property
    def is_composition(self) -> bool:
        if self.cascade_delete or self.has_delete_orphan:
            return True
        return (self.ondelete or "").upper() == "CASCADE"


@dataclass
class ParsedEnum:
    """StrEnum 또는 Enum 클래스."""

    name: str
    symbol_id: str
    source_span: SourceSpan
    base_class: str
    members: list[str] = field(default_factory=list)


@dataclass
class ParsedClass:
    """SQLModel/Pydantic/일반 클래스 하나."""

    name: str
    symbol_id: str
    source_span: SourceSpan
    base_classes: list[str] = field(default_factory=list)
    base_symbol_ids: list[str] = field(default_factory=list)
    is_table: bool = False
    tablename: str | None = None
    fields: list[ParsedField] = field(default_factory=list)
    relationships: list[ParsedRelationship] = field(default_factory=list)
    methods: list[ParsedMethod] = field(default_factory=list)
    docstring: str | None = None
    model_config: dict[str, str] = field(default_factory=dict)
    stereotypes: list[str] = field(default_factory=list)
    is_abstract: bool = False
    is_protocol_like: bool = False

    @property
    def is_join_table(self) -> bool:
        """구조적 판별: FK 2개 이상, 관계 없음, 데이터 필드 없음."""

        if not self.is_table:
            return False
        fk_fields = [field for field in self.fields if field.foreign_key]
        if len(fk_fields) < 2 or self.relationships:
            return False
        non_fk_non_pk = [field for field in self.fields if not field.foreign_key and not field.is_primary_key]
        return len(non_fk_non_pk) == 0


@dataclass
class ParsedModule:
    """하나의 모델 파일 파싱 결과."""

    domain_name: str
    file_path: Path
    classes: list[ParsedClass] = field(default_factory=list)
    enums: list[ParsedEnum] = field(default_factory=list)


@dataclass
class DomainSchema:
    """전체 파싱 결과 (여러 모듈 합산)."""

    modules: list[ParsedModule] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def all_classes(self) -> list[ParsedClass]:
        return [cls for module in self.modules for cls in module.classes]

    def all_enums(self) -> list[ParsedEnum]:
        return [enum for module in self.modules for enum in module.enums]

    def all_symbols(self) -> list[ParsedClass | ParsedEnum]:
        return [*self.all_classes(), *self.all_enums()]

    def get_symbol(self, symbol_id: str) -> ParsedClass | ParsedEnum | None:
        for symbol in self.all_symbols():
            if symbol.symbol_id == symbol_id:
                return symbol
        return None
