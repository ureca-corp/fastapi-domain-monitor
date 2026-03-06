"""FastAPI 라우터 + WebSocket + 상태 관리 플러그인."""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

from fastapi_domain_monitor.mermaid import DETAIL_LEVELS, generate_mermaid
from fastapi_domain_monitor.models import DomainSchema, ParsedClass, ParsedEnum
from fastapi_domain_monitor.parser import DEFAULT_WATCH_PATTERNS, parse_directory
from fastapi_domain_monitor.watcher import ModelFileWatcher

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
        detail_level: str,
        show_base_fields: bool,
    ) -> None:
        self.watch_dirs = watch_dirs
        self.watch_patterns = watch_patterns
        self.detail_level = detail_level
        self.show_base_fields = show_base_fields
        self.schema: DomainSchema | None = None
        self.default_mermaid_text: str = ""
        self.clients: set[WebSocket] = set()
        self.last_error: str | None = None

    async def refresh(self) -> None:
        """파일 재파싱 + 연결된 WebSocket 클라이언트 모두에게 push."""

        try:
            schema = parse_directory(self.watch_dirs, watch_patterns=list(self.watch_patterns))
            self.schema = schema
            self.default_mermaid_text = self.render_mermaid()
            self.last_error = None
            await self.broadcast(
                {
                    "type": "update",
                    "mermaid": self.default_mermaid_text,
                    "schema": self.schema_payload(),
                    "defaults": self.defaults_payload(),
                }
            )
        except Exception as exc:
            logging.warning("fastapi-domain-monitor: parse error: %s", exc)
            self.schema = None
            self.default_mermaid_text = ""
            self.last_error = str(exc)
            await self.broadcast({"type": "error", "message": str(exc), "defaults": self.defaults_payload()})

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
    ) -> str:
        if self.schema is None:
            return ""
        return generate_mermaid(
            self.schema,
            show_base_fields=self.show_base_fields if show_base_fields is None else show_base_fields,
            detail_level=self.detail_level if detail_level is None else detail_level,
            visible_domains=set(domains) if domains else None,
        )

    def source_payload(self, symbol_id: str) -> dict[str, Any] | None:
        if self.schema is None:
            return None
        symbol = self.schema.get_symbol(symbol_id)
        if symbol is None:
            return None
        file_path = symbol.source_span.file_path
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        lines = file_path.read_text(encoding="utf-8").splitlines()
        start = symbol.source_span.start_line
        end = symbol.source_span.end_line
        excerpt = "\n".join(lines[start - 1:end])
        kind = "class" if isinstance(symbol, ParsedClass) else "enum"
        return {
            "symbol_id": symbol.symbol_id,
            "name": symbol.name,
            "kind": kind,
            "file_path": str(file_path),
            "start_line": start,
            "end_line": end,
            "excerpt": excerpt,
        }

    def file_payload(self, file_path: str) -> dict[str, Any] | None:
        resolved_file_path = self._resolve_monitored_file(file_path)
        if resolved_file_path is None:
            return None
        if not resolved_file_path.exists() or not resolved_file_path.is_file():
            raise FileNotFoundError(resolved_file_path)

        content = resolved_file_path.read_text(encoding="utf-8")
        line_count = content.count("\n") + (1 if content else 0)
        return {
            "file_path": str(resolved_file_path),
            "name": resolved_file_path.name,
            "content": content,
            "line_count": line_count,
        }

    def _resolve_monitored_file(self, file_path: str) -> Path | None:
        candidate = Path(file_path).expanduser()
        try:
            resolved = candidate.resolve(strict=False)
        except RuntimeError:
            return None

        for watch_dir in self.watch_dirs:
            try:
                resolved.relative_to(watch_dir.resolve())
            except ValueError:
                continue
            return resolved
        return None

    async def broadcast(self, message: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.clients.discard(ws)


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
        "<p>Built frontend assets were not found. Run the frontend export step and sync the output into "
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
    detail_level: str = "compact",
) -> None:
    """FastAPI 앱에 도메인 모니터 플러그인 마운트."""

    if not enabled:
        return
    if detail_level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {detail_level}")

    resolved_dirs = _resolve_watch_dirs(watch_dirs)
    resolved_patterns = tuple(watch_patterns or DEFAULT_WATCH_PATTERNS)
    state = MonitorState(
        watch_dirs=resolved_dirs,
        watch_patterns=resolved_patterns,
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
    ):
        effective_detail = detail_level or state.detail_level
        if effective_detail not in DETAIL_LEVELS:
            raise HTTPException(status_code=400, detail="Unsupported detail level")
        mermaid_text = state.render_mermaid(
            domains=_parse_domains(domains),
            detail_level=effective_detail,
            show_base_fields=show_base_fields,
        )
        return PlainTextResponse(mermaid_text)

    @router.get("/api/source/{symbol_id}", response_class=JSONResponse)
    async def get_source(symbol_id: str):
        try:
            payload = state.source_payload(symbol_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Source file not found") from None
        if payload is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        return JSONResponse(content=payload)

    @router.get("/api/file", response_class=JSONResponse)
    async def get_file(file_path: str = Query(...)):
        try:
            payload = state.file_payload(file_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found") from None
        if payload is None:
            raise HTTPException(status_code=404, detail="File not found")
        return JSONResponse(content=payload)

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        state.clients.add(ws)
        try:
            if state.last_error:
                await ws.send_json({"type": "error", "message": state.last_error, "defaults": state.defaults_payload()})
            else:
                await ws.send_json(
                    {
                        "type": "update",
                        "mermaid": state.default_mermaid_text,
                        "schema": state.schema_payload(),
                        "defaults": state.defaults_payload(),
                    }
                )
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            state.clients.discard(ws)

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app_instance: FastAPI):
        watcher: ModelFileWatcher | None = None
        async with original_lifespan(app_instance):
            await state.refresh()
            watcher = ModelFileWatcher(
                watch_dirs=resolved_dirs,
                watch_patterns=resolved_patterns,
                on_change=state.refresh,
            )
            loop = asyncio.get_running_loop()
            watcher.start(loop)
            try:
                yield
            finally:
                if watcher is not None:
                    watcher.stop()

    app.router.lifespan_context = combined_lifespan

    _mount_static_assets(app)
    app.include_router(router, prefix=mount_path)
