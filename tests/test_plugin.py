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


def test_schema_mermaid_and_source_endpoints(tmp_path):
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

        account_symbol = next(
            item["symbol_id"]
            for module in schema["modules"]
            if module["domain_name"] == "accounts"
            for item in module["classes"]
            if item["name"] == "AccountSchema"
        )

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

        source_response = client.get(f"/domain-monitor/api/source/{account_symbol}")
        assert source_response.status_code == 200
        source = source_response.json()
        assert source["name"] == "AccountSchema"
        assert "class AccountSchema" in source["excerpt"]

        file_response = client.get(
            "/domain-monitor/api/file",
            params={"file_path": source["file_path"]},
        )
        assert file_response.status_code == 200
        file_payload = file_response.json()
        assert file_payload["name"] == "schemas.py"
        assert "class AccountSchema" in file_payload["content"]


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


def test_custom_mount_path_serves_html_api_and_websocket(tmp_path):
    _write_fixture(tmp_path)
    app = FastAPI()
    setup_domain_monitor(app, watch_dirs=[tmp_path], mount_path="/custom-monitor")

    with TestClient(app) as client:
        html_response = client.get("/custom-monitor")
        assert html_response.status_code == 200
        assert STATIC_ASSET_PREFIX in html_response.text

        schema_response = client.get("/custom-monitor/api/schema")
        assert schema_response.status_code == 200

        with client.websocket_connect("/custom-monitor/ws") as websocket:
            initial = websocket.receive_json()

    assert initial["type"] == "update"
    assert "schema" in initial
