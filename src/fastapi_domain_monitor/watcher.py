"""watchdog 기반 파일 변경 감지 - *_models.py 패턴 파일 감시."""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class ModelFileWatcher(FileSystemEventHandler):
    """*_models.py 파일 변경 감지 후 async 콜백 호출."""

    def __init__(
        self,
        watch_dirs: list[str | Path],
        on_change: Callable[[], Coroutine],
        debounce_ms: int = 300,
    ):
        super().__init__()
        self._watch_dirs = [Path(d) for d in watch_dirs]
        self._on_change = on_change
        self._debounce_s = debounce_ms / 1000.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._observer = Observer()
        self._timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """watchdog Observer 시작."""
        self._loop = loop
        for d in self._watch_dirs:
            path = Path(d)
            if path.is_dir():
                self._observer.schedule(self, str(path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        """Observer 중지."""
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._observer.stop()
        self._observer.join()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src = event.src_path
        if not src.endswith("_models.py"):
            return
        self._schedule_callback()

    def _schedule_callback(self) -> None:
        """debounce: 기존 타이머 cancel 후 새 타이머 시작."""
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.start()

    def _fire(self) -> None:
        """스레드 → asyncio 브릿지."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_change(), self._loop)
