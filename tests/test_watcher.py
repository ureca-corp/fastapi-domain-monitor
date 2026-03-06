"""watcher.py 단위 테스트."""
from pathlib import Path

from fastapi_domain_monitor.watcher import ModelFileWatcher


async def _noop():
    return None


def test_watcher_matches_extended_patterns(tmp_path):
    watcher = ModelFileWatcher(
        watch_dirs=[Path(tmp_path)],
        watch_patterns=["schemas.py", "dto.py"],
        on_change=_noop,
    )

    assert watcher._matches_patterns("schemas.py") is True
    assert watcher._matches_patterns("dto.py") is True
    assert watcher._matches_patterns("helpers.py") is False
