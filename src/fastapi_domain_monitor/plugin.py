"""FastAPI 라우터 + WebSocket + 상태 관리 플러그인."""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.routing import APIRouter

from fastapi_domain_monitor.models import DomainSchema
from fastapi_domain_monitor.watcher import ModelFileWatcher


class MonitorState:
    """플러그인 런타임 상태."""

    def __init__(self) -> None:
        self.schema: DomainSchema | None = None
        self.mermaid_text: str = ""
        self.clients: set[WebSocket] = set()

    async def refresh(self, watch_dirs: list[Path], show_base_fields: bool) -> None:
        """파일 재파싱 + 연결된 WebSocket 클라이언트 모두에게 push."""
        from fastapi_domain_monitor.mermaid import generate_mermaid
        from fastapi_domain_monitor.parser import parse_directory

        self.schema = parse_directory(watch_dirs)
        self.mermaid_text = generate_mermaid(self.schema, show_base_fields=show_base_fields)
        await self.broadcast({"type": "update", "mermaid": self.mermaid_text})

    async def broadcast(self, message: dict) -> None:
        """연결된 모든 WebSocket 클라이언트에게 메시지 전송. 끊긴 연결 자동 제거."""
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
        return {k: _serialize(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _resolve_watch_dirs(watch_dirs: list[str | Path] | None) -> list[Path]:
    if watch_dirs:
        return [Path(d) for d in watch_dirs]
    candidate = Path.cwd() / "src" / "modules"
    if candidate.is_dir():
        return [candidate]
    return [Path.cwd()]


def _load_spa_html() -> str:
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<html><body><h1>Domain Monitor</h1><p>static/index.html not found.</p></body></html>"


def setup_domain_monitor(
    app: FastAPI,
    watch_dirs: list[str | Path] | None = None,
    mount_path: str = "/domain-monitor",
    enabled: bool = True,
    show_base_fields: bool = False,
) -> None:
    """FastAPI 앱에 도메인 모니터 플러그인 마운트."""
    if not enabled:
        return

    resolved_dirs = _resolve_watch_dirs(watch_dirs)
    state = MonitorState()
    watcher: ModelFileWatcher | None = None
    router = APIRouter()

    # --- Endpoints ---

    @router.get("/", response_class=HTMLResponse)
    async def spa_index():
        return HTMLResponse(_load_spa_html())

    @router.get("/api/schema", response_class=JSONResponse)
    async def get_schema():
        if state.schema is None:
            return JSONResponse(content={})
        return JSONResponse(content=_serialize(state.schema))

    @router.get("/api/mermaid", response_class=PlainTextResponse)
    async def get_mermaid():
        return PlainTextResponse(state.mermaid_text)

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        state.clients.add(ws)
        try:
            await ws.send_json({"type": "update", "mermaid": state.mermaid_text})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            state.clients.discard(ws)

    # --- Lifecycle ---

    @app.on_event("startup")
    async def _startup():
        nonlocal watcher
        await state.refresh(resolved_dirs, show_base_fields)
        watcher = ModelFileWatcher(
            watch_dirs=resolved_dirs,
            on_change=lambda: state.refresh(resolved_dirs, show_base_fields),
        )
        loop = asyncio.get_running_loop()
        watcher.start(loop)

    @app.on_event("shutdown")
    async def _shutdown():
        nonlocal watcher
        if watcher is not None:
            watcher.stop()
            watcher = None

    app.include_router(router, prefix=mount_path)
