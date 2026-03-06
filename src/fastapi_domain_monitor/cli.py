"""
domain-monitor CLI - 단독 실행 서버.
"""
from __future__ import annotations

import threading
import webbrowser

import click
import uvicorn

from fastapi_domain_monitor import setup_domain_monitor
from fastapi_domain_monitor.parser import DEFAULT_WATCH_PATTERNS


@click.group()
@click.version_option(package_name="fastapi-domain-monitor")
def cli():
    """FastAPI Domain Monitor — Pydantic/SQLModel 다이어그램 대시보드"""


@cli.command()
@click.option(
    "--watch",
    "-w",
    multiple=True,
    default=["src/modules"],
    show_default=True,
    help="감시할 디렉터리 (여러 번 사용 가능)",
    metavar="DIR",
)
@click.option(
    "--watch-pattern",
    multiple=True,
    default=DEFAULT_WATCH_PATTERNS,
    show_default=True,
    help="감시할 파일 패턴 (여러 번 사용 가능)",
    metavar="GLOB",
)
@click.option("--port", "-p", default=7842, show_default=True, help="서버 포트")
@click.option("--host", default="127.0.0.1", show_default=True, help="서버 호스트")
@click.option("--open/--no-open", default=True, help="브라우저 자동 열기")
@click.option("--show-base-fields", is_flag=True, default=False, help="id/created_at 등 기본 필드 표시")
@click.option(
    "--detail-level",
    type=click.Choice(["compact", "full"], case_sensitive=False),
    default="compact",
    show_default=True,
    help="다이어그램 상세도",
)
def start(watch, watch_pattern, port, host, open, show_base_fields, detail_level):
    """도메인 모니터 서버를 시작합니다."""

    from fastapi import FastAPI

    app = FastAPI(title="Domain Monitor")
    setup_domain_monitor(
        app,
        watch_dirs=list(watch),
        watch_patterns=list(watch_pattern),
        show_base_fields=show_base_fields,
        detail_level=detail_level.lower(),
    )

    url = f"http://{host}:{port}/domain-monitor"
    click.echo(click.style("FastAPI Domain Monitor", fg="green", bold=True))
    click.echo(f"  → {url}")
    click.echo(f"  → watching: {', '.join(watch)}")
    click.echo(f"  → patterns: {', '.join(watch_pattern)}")
    click.echo(f"  → detail: {detail_level.lower()}")
    click.echo("  Press Ctrl+C to stop\n")

    if open:
        def _open_browser():
            import time

            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main():
    cli()
