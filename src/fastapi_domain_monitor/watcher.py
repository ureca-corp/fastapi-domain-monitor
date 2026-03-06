"""watchdog 기반 파일 변경 감지."""
from __future__ import annotations

import asyncio
import fnmatch
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from fastapi_domain_monitor.parser import DEFAULT_WATCH_PATTERNS


class ModelFileWatcher(FileSystemEventHandler):
    """모델 파일 변경 감지 후 async 콜백 호출."""

    def __init__(
        self,
        watch_dirs: list[str | Path],
        on_change: Callable[[], Coroutine],
        debounce_ms: int = 300,
        watch_patterns: list[str] | tuple[str, ...] | None = None,
    ):
        super().__init__()
        self._watch_dirs = [Path(directory) for directory in watch_dirs]
        self._watch_patterns = tuple(watch_patterns or DEFAULT_WATCH_PATTERNS)
        self._on_change = on_change
        self._debounce_s = debounce_ms / 1000.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._observer = Observer()
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        for directory in self._watch_dirs:
            if directory.is_dir():
                self._observer.schedule(self, str(directory), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._observer.stop()
        self._observer.join()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = Path(event.src_path).name
        dest = Path(getattr(event, "dest_path", "")).name if getattr(event, "dest_path", None) else None
        if not (self._matches_patterns(src) or (dest and self._matches_patterns(dest))):
            return
        self._schedule_callback()

    def _matches_patterns(self, filename: str) -> bool:
        if filename == "__init__.py":
            return False
        return any(fnmatch.fnmatch(filename, pattern) for pattern in self._watch_patterns)

    def _schedule_callback(self) -> None:
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.start()

    def _fire(self) -> None:
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_change(), self._loop)
