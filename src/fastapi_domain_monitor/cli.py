"""
domain-monitor CLI - supabase start 같은 단독 실행 서버.

사용법:
    domain-monitor start                      # src/modules 자동 감지
    domain-monitor start --watch src/modules  # 경로 직접 지정
    domain-monitor start --port 9000          # 포트 변경
"""
import threading
import webbrowser
import click
import uvicorn

from fastapi_domain_monitor import setup_domain_monitor


@click.group()
@click.version_option(package_name="fastapi-domain-monitor")
def cli():
    """FastAPI Domain Monitor — SQLModel 도메인 다이어그램 대시보드"""


@cli.command()
@click.option(
    "--watch", "-w",
    multiple=True,
    default=["src/modules"],
    show_default=True,
    help="감시할 디렉터리 (여러 번 사용 가능)",
    metavar="DIR",
)
@click.option("--port", "-p", default=7842, show_default=True, help="서버 포트")
@click.option("--host", default="127.0.0.1", show_default=True, help="서버 호스트")
@click.option("--open/--no-open", default=True, help="브라우저 자동 열기")
@click.option("--show-base-fields", is_flag=True, default=False, help="id/created_at 등 기본 필드 표시")
def start(watch, port, host, open, show_base_fields):
    """도메인 모니터 서버를 시작합니다."""
    from fastapi import FastAPI

    app = FastAPI(title="Domain Monitor")
    setup_domain_monitor(
        app,
        watch_dirs=list(watch),
        show_base_fields=show_base_fields,
    )

    url = f"http://{host}:{port}/domain-monitor"
    click.echo(click.style("FastAPI Domain Monitor", fg="green", bold=True))
    click.echo(f"  → {url}")
    click.echo(f"  → watching: {', '.join(watch)}")
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
