"""FastAPI 라우터 + 상태 관리 플러그인."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

from fastapi_domain_monitor.mermaid import DETAIL_LEVELS, generate_mermaid
from fastapi_domain_monitor.models import DomainSchema
from fastapi_domain_monitor.parser import DEFAULT_WATCH_PATTERNS, parse_directory

STATIC_ROOT = Path(__file__).parent / "static"
STATIC_EXPORT_DIR = STATIC_ROOT / "dashboard"
STATIC_ASSET_PREFIX = "/_fastapi-domain-monitor-static"


class MonitorState:
    """플러그인 런타임 상태."""

    def __init__(
        self,
        *,
        watch_dirs: list[Path],
        watch_patterns: tuple[str, ...],
        watch_class_bases: tuple[str, ...] | None,
        detail_level: str,
        show_base_fields: bool,
    ) -> None:
        self.watch_dirs = watch_dirs
        self.watch_patterns = watch_patterns
        self.watch_class_bases = watch_class_bases
        self.detail_level = detail_level
        self.show_base_fields = show_base_fields
        self.schema: DomainSchema | None = None
        self.default_mermaid_text: str = ""
        self.last_error: str | None = None

    async def refresh(self) -> None:
        """파일 재파싱 (스레드에서 실행하여 이벤트 루프 블로킹 방지)."""
        try:
            schema = await asyncio.to_thread(
                parse_directory,
                self.watch_dirs,
                watch_patterns=list(self.watch_patterns),
                watch_class_bases=list(self.watch_class_bases) if self.watch_class_bases else None,
            )
            self.schema = schema
            self.default_mermaid_text = self.render_mermaid()
            self.last_error = None
        except Exception as exc:
            logging.warning("fastapi-domain-monitor: parse error: %s", exc)
            self.schema = None
            self.default_mermaid_text = ""
            self.last_error = str(exc)

    def defaults_payload(self) -> dict[str, Any]:
        return {
            "detail_level": self.detail_level,
            "show_base_fields": self.show_base_fields,
            "watch_patterns": list(self.watch_patterns),
        }

    def schema_payload(self) -> dict[str, Any]:
        if self.schema is None:
            return {"modules": [], "generated_at": None, "defaults": self.defaults_payload()}
        payload = _serialize(self.schema)
        payload["defaults"] = self.defaults_payload()
        return payload

    def render_mermaid(
        self,
        *,
        domains: list[str] | None = None,
        detail_level: str | None = None,
        show_base_fields: bool | None = None,
        stereotypes: list[str] | None = None,
    ) -> str:
        if self.schema is None:
            return ""
        return generate_mermaid(
            self.schema,
            show_base_fields=self.show_base_fields if show_base_fields is None else show_base_fields,
            detail_level=self.detail_level if detail_level is None else detail_level,
            visible_domains=set(domains) if domains else None,
            visible_stereotypes=set(stereotypes) if stereotypes is not None else None,
        )


def _serialize(obj: Any) -> Any:
    """dataclass / datetime → JSON-safe dict."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {key: _serialize(value) for key, value in dataclasses.asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    return obj


def _resolve_watch_dirs(watch_dirs: list[str | Path] | None) -> list[Path]:
    if watch_dirs:
        return [Path(directory) for directory in watch_dirs]
    candidate = Path.cwd() / "src" / "modules"
    if candidate.is_dir():
        return [candidate]
    return [Path.cwd()]


def _load_spa_html() -> str:
    html_path = _static_dir() / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return (
        "<html><body><h1>Domain Monitor</h1>"
        "<p>Built frontend assets were not found. Run the frontend build step and sync the output into "
        "fastapi_domain_monitor/static.</p></body></html>"
    )


def _static_dir() -> Path:
    if STATIC_EXPORT_DIR.is_dir():
        return STATIC_EXPORT_DIR
    return STATIC_ROOT


def _mount_static_assets(app: FastAPI) -> None:
    if any(isinstance(route, Mount) and route.path == STATIC_ASSET_PREFIX for route in app.router.routes):
        return
    app.mount(
        STATIC_ASSET_PREFIX,
        StaticFiles(directory=_static_dir(), html=False, check_dir=False),
        name="fastapi-domain-monitor-static",
    )


def _parse_domains(domains: str | None) -> list[str] | None:
    if not domains:
        return None
    items = [item.strip() for item in domains.split(",") if item.strip()]
    return items or None


def setup_domain_monitor(
    app: FastAPI,
    watch_dirs: list[str | Path] | None = None,
    mount_path: str = "/domain-monitor",
    enabled: bool = True,
    show_base_fields: bool = True,
    watch_patterns: list[str] | tuple[str, ...] | None = None,
    watch_class_bases: list[str] | tuple[str, ...] | None = None,
    detail_level: str = "compact",
) -> None:
    """FastAPI 앱에 도메인 모니터 플러그인 마운트."""
    if not enabled:
        return
    if detail_level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {detail_level}")

    resolved_dirs = _resolve_watch_dirs(watch_dirs)
    resolved_patterns = tuple(watch_patterns or DEFAULT_WATCH_PATTERNS)
    resolved_class_bases = tuple(watch_class_bases) if watch_class_bases else None
    state = MonitorState(
        watch_dirs=resolved_dirs,
        watch_patterns=resolved_patterns,
        watch_class_bases=resolved_class_bases,
        detail_level=detail_level,
        show_base_fields=show_base_fields,
    )
    router = APIRouter()

    @router.get("", response_class=HTMLResponse)
    @router.get("/", response_class=HTMLResponse)
    async def spa_index():
        index_path = _static_dir() / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_load_spa_html())

    @router.get("/api/schema", response_class=JSONResponse)
    async def get_schema():
        return JSONResponse(content=state.schema_payload())

    @router.get("/api/mermaid", response_class=PlainTextResponse)
    async def get_mermaid(
        domains: str | None = Query(default=None),
        detail_level: str | None = Query(default=None),
        show_base_fields: bool | None = Query(default=None),
        stereotypes: str | None = Query(default=None),
    ):
        effective_detail = detail_level or state.detail_level
        if effective_detail not in DETAIL_LEVELS:
            raise HTTPException(status_code=400, detail="Unsupported detail level")
        mermaid_text = state.render_mermaid(
            domains=_parse_domains(domains),
            detail_level=effective_detail,
            show_base_fields=show_base_fields,
            stereotypes=_parse_domains(stereotypes),
        )
        return PlainTextResponse(mermaid_text)

    @router.post("/api/refresh", response_class=JSONResponse)
    async def post_refresh():
        await state.refresh()
        if state.last_error:
            return JSONResponse(
                content={"error": state.last_error},
                status_code=500,
            )
        return JSONResponse(content=state.schema_payload())

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app_instance: FastAPI):
        async with original_lifespan(app_instance):
            await state.refresh()
            yield

    app.router.lifespan_context = combined_lifespan

    _mount_static_assets(app)
    app.include_router(router, prefix=mount_path)
