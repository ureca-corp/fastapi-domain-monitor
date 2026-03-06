"""
중간 표현(IR) - AST 파서와 Mermaid 생성기 사이의 공유 데이터 구조.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ParsedField:
    """클래스의 필드 하나."""
    name: str
    type_annotation: str          # 원본 타입 문자열 (e.g. "str", "UUID", "str | None")
    is_primary_key: bool = False
    is_nullable: bool = False
    has_default: bool = False
    foreign_key: str | None = None  # e.g. "accounts.id"
    is_sa_column: bool = False      # sa_column= 으로 정의된 필드
    is_json: bool = False


@dataclass
class ParsedRelationship:
    """SQLModel Relationship() 필드."""
    field_name: str
    target_class: str            # 참조하는 클래스 이름 (forward ref 해제 후)
    back_populates: str | None = None
    is_list: bool = False        # list["X"] 형태
    link_model: str | None = None   # N:M 조인 테이블 클래스 이름
    uselist_false: bool = False  # sa_relationship_kwargs={"uselist": False}


@dataclass
class ParsedEnum:
    """StrEnum 또는 Enum 클래스."""
    name: str
    base_class: str              # "StrEnum", "IntEnum", "Enum"
    members: list[str] = field(default_factory=list)


@dataclass
class ParsedClass:
    """SQLModel 클래스 하나 (테이블 or 일반 모델)."""
    name: str
    base_classes: list[str] = field(default_factory=list)
    is_table: bool = False       # table=True 키워드
    tablename: str | None = None  # __tablename__
    fields: list[ParsedField] = field(default_factory=list)
    relationships: list[ParsedRelationship] = field(default_factory=list)
    docstring: str | None = None

    @property
    def is_join_table(self) -> bool:
        """SQLModel 직접 상속(BaseModel 아님) → join 테이블 패턴."""
        return self.is_table and "SQLModel" in self.base_classes and "BaseModel" not in self.base_classes


@dataclass
class ParsedModule:
    """하나의 _models.py 파일 파싱 결과."""
    domain_name: str             # 파일 경로에서 추출한 도메인 이름 (e.g. "students")
    file_path: Path
    classes: list[ParsedClass] = field(default_factory=list)
    enums: list[ParsedEnum] = field(default_factory=list)


@dataclass
class DomainSchema:
    """전체 파싱 결과 (여러 모듈 합산)."""
    modules: list[ParsedModule] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def all_classes(self) -> list[ParsedClass]:
        return [cls for m in self.modules for cls in m.classes]

    def all_enums(self) -> list[ParsedEnum]:
        return [e for m in self.modules for e in m.enums]
