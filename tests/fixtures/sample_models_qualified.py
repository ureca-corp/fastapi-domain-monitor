"""
Qualified name 패턴 테스트용 fixture.
typing.Optional, typing.List, enum.StrEnum, sqlmodel.Field, sqlmodel.Relationship
등 모듈 접두사 사용 패턴 검증.
link_model=module.Class, sa_column=sqlalchemy.Column(sqlmodel.JSON) 패턴 포함.
"""
import enum
import typing
from uuid import UUID

import sqlalchemy
import sqlmodel


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Order(sqlmodel.SQLModel, table=True):
    __tablename__ = "orders"

    id: UUID = sqlmodel.Field(primary_key=True)
    status: OrderStatus = sqlmodel.Field(default=OrderStatus.PENDING)
    note: typing.Optional[str] = None
    tags: typing.List[str] = sqlmodel.Field(default_factory=list)
    items: typing.List["Item"] = sqlmodel.Relationship(back_populates="order")


class Item(sqlmodel.SQLModel, table=True):
    __tablename__ = "items"

    id: UUID = sqlmodel.Field(primary_key=True)
    order_id: UUID = sqlmodel.Field(foreign_key="orders.id")
    name: str
    order: "Order" = sqlmodel.Relationship(back_populates="items")


# ── qualified link_model (module.Class 패턴) ──────────────────

class PostTag(sqlmodel.SQLModel, table=True):
    __tablename__ = "post_tags"

    post_id: UUID = sqlmodel.Field(foreign_key="posts.id")
    tag_id: UUID = sqlmodel.Field(foreign_key="tags.id")


class Post(sqlmodel.SQLModel, table=True):
    __tablename__ = "posts"

    id: UUID = sqlmodel.Field(primary_key=True)
    # link_model을 모듈 접두사로 참조하는 패턴
    tags: typing.List["Tag"] = sqlmodel.Relationship(
        back_populates="posts",
        link_model=links.PostTag,  # ast.Attribute 패턴
    )


class Tag(sqlmodel.SQLModel, table=True):
    __tablename__ = "tags"

    id: UUID = sqlmodel.Field(primary_key=True)
    posts: typing.List["Post"] = sqlmodel.Relationship(
        back_populates="tags",
        link_model=links.PostTag,
    )


# ── qualified JSON column (sqlalchemy.Column(sqlmodel.JSON)) ──

class Report(sqlmodel.SQLModel, table=True):
    __tablename__ = "reports"

    id: UUID = sqlmodel.Field(primary_key=True)
    payload: dict = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlmodel.JSON),
    )
