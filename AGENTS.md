## Diagram-Friendly Pydantic And SQLModel Rules

When updating Python models in this repository, prefer declarations that keep structure visible to static AST parsing so `fastapi-domain-monitor` can render accurate Mermaid diagrams.

- Put models in discoverable files: `*_models.py`, `models.py`, `*_schemas.py`, `schemas.py`, `*_entities.py`, `entities.py`, `*_dto.py`, `dto.py`.
- Declare ORM relations with `Relationship(...)`.
- Prefer direct type annotations for nested models and enums, for example `status: ExamStatus` and `items: list[LineItem]`.
- If an enum-backed field must remain `str`, expose the enum statically with at least one of these:
  - enum default value such as `status: str = Field(default=ExamStatus.DRAFT)`
  - SQLAlchemy enum column such as `sa_column=Column(SAEnum(ExamStatus, ...))`
  - trailing field comment such as `status: str  # ExamStatus`
  - class method logic such as `return self.status == ExamStatus.DRAFT`
- Keep `table=True`, `__tablename__`, `model_config`, and `ConfigDict` explicitly in the class body.
- Avoid runtime-only schema generation patterns if diagram fidelity matters.
