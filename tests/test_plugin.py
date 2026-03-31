"""plugin.py API 테스트."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_domain_monitor import setup_domain_monitor
from fastapi_domain_monitor import plugin as plugin_module
from fastapi_domain_monitor.plugin import STATIC_ASSET_PREFIX


def _write_fixture(tmp_path):
    accounts_dir = tmp_path / "accounts"
    billing_dir = tmp_path / "billing"
    accounts_dir.mkdir()
    billing_dir.mkdir()

    (accounts_dir / "schemas.py").write_text(
        """
from pydantic import BaseModel, ConfigDict, computed_field


class Address(BaseModel):
    city: str


class AccountSchema(BaseModel):
    \"\"\"Account schema.\"\"\"
    model_config = ConfigDict(title="AccountSchema", extra="forbid")

    email: str
    address: Address

    @computed_field
    @property
    def label(self) -> str:
        return self.email
""",
        encoding="utf-8",
    )

    (billing_dir / "dto.py").write_text(
        """
class InvoiceDTO:
    total: int
""",
        encoding="utf-8",
    )


def test_schema_and_mermaid_endpoints(tmp_path):
    _write_fixture(tmp_path)
    app = FastAPI()
    setup_domain_monitor(
        app,
        watch_dirs=[tmp_path],
        watch_patterns=["schemas.py", "dto.py"],
        detail_level="compact",
    )

    with TestClient(app) as client:
        html_response = client.get("/domain-monitor")
        assert html_response.status_code == 200
        assert STATIC_ASSET_PREFIX in html_response.text

        html_response_with_slash = client.get("/domain-monitor/")
        assert html_response_with_slash.status_code == 200

        schema_response = client.get("/domain-monitor/api/schema")
        assert schema_response.status_code == 200
        schema = schema_response.json()
        assert schema["defaults"]["detail_level"] == "compact"
        assert {module["domain_name"] for module in schema["modules"]} == {"accounts", "billing"}

        compact_mermaid = client.get(
            "/domain-monitor/api/mermaid",
            params={"domains": "accounts", "detail_level": "compact", "show_base_fields": "false"},
        )
        assert compact_mermaid.status_code == 200
        assert "Account schema." not in compact_mermaid.text
        assert "InvoiceDTO" not in compact_mermaid.text

        unsupported_mermaid = client.get(
            "/domain-monitor/api/mermaid",
            params={"domains": "accounts", "detail_level": "full", "show_base_fields": "false"},
        )
        assert unsupported_mermaid.status_code == 400
        assert unsupported_mermaid.json()["detail"] == "Unsupported detail level"


def test_post_refresh_reparses_files(tmp_path):
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    (accounts_dir / "schemas.py").write_text(
        "class OriginalModel:\n    id: int\n",
        encoding="utf-8",
    )

    app = FastAPI()
    setup_domain_monitor(app, watch_dirs=[tmp_path], watch_patterns=["schemas.py"])

    with TestClient(app) as client:
        schema = client.get("/domain-monitor/api/schema").json()
        class_names = {c["name"] for m in schema["modules"] for c in m["classes"]}
        assert "OriginalModel" in class_names

        # 파일 변경 시뮬레이션
        (accounts_dir / "schemas.py").write_text(
            "class UpdatedModel:\n    id: int\n",
            encoding="utf-8",
        )

        # refresh 전에는 캐시된 결과
        schema_before = client.get("/domain-monitor/api/schema").json()
        class_names_before = {c["name"] for m in schema_before["modules"] for c in m["classes"]}
        assert "OriginalModel" in class_names_before

        # POST /api/refresh 로 재파싱
        refresh_response = client.post("/domain-monitor/api/refresh")
        assert refresh_response.status_code == 200
        refreshed = refresh_response.json()
        class_names_after = {c["name"] for m in refreshed["modules"] for c in m["classes"]}
        assert "UpdatedModel" in class_names_after
        assert "OriginalModel" not in class_names_after


def test_static_assets_are_served():
    app = FastAPI()
    setup_domain_monitor(app)

    static_dir = plugin_module._static_dir()
    asset_path = next(
        (path for path in static_dir.rglob("*") if path.is_file() and path.name != "index.html"),
        None,
    )
    assert asset_path is not None

    with TestClient(app) as client:
        response = client.get(f"{STATIC_ASSET_PREFIX}/{asset_path.relative_to(static_dir).as_posix()}")

    assert response.status_code == 200


def test_setup_domain_monitor_rejects_full_detail_level():
    app = FastAPI()

    with pytest.raises(ValueError, match="Unsupported detail level"):
        setup_domain_monitor(app, detail_level="full")


def test_custom_mount_path_serves_html_and_api(tmp_path):
    _write_fixture(tmp_path)
    app = FastAPI()
    setup_domain_monitor(app, watch_dirs=[tmp_path], mount_path="/custom-monitor")

    with TestClient(app) as client:
        html_response = client.get("/custom-monitor")
        assert html_response.status_code == 200
        assert STATIC_ASSET_PREFIX in html_response.text

        schema_response = client.get("/custom-monitor/api/schema")
        assert schema_response.status_code == 200

        refresh_response = client.post("/custom-monitor/api/refresh")
        assert refresh_response.status_code == 200
