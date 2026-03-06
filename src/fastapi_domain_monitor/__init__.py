"""
fastapi-domain-monitor: FastAPI 앱에 한 줄로 마운트하는 도메인 다이어그램 플러그인.

사용법:
    from fastapi_domain_monitor import setup_domain_monitor

    app = FastAPI(...)
    setup_domain_monitor(app, watch_dirs=["src/modules"])
    # → http://localhost:8000/domain-monitor
"""
from fastapi_domain_monitor.plugin import setup_domain_monitor

__all__ = ["setup_domain_monitor"]
__version__ = "0.1.6"
