"""plugin.py API 테스트."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_domain_monitor import setup_domain_monitor


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
        detail_level="full",
    )

    with TestClient(app) as client:
        schema_response = client.get("/domain-monitor/api/schema")
        assert schema_response.status_code == 200
        schema = schema_response.json()
        assert schema["defaults"]["detail_level"] == "full"
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

        full_mermaid = client.get(
            "/domain-monitor/api/mermaid",
            params={"domains": "accounts", "detail_level": "full", "show_base_fields": "false"},
        )
        assert full_mermaid.status_code == 200
        assert "Account schema." in full_mermaid.text
        assert "config: extra=forbid, title=AccountSchema" in full_mermaid.text

        source_response = client.get(f"/domain-monitor/api/source/{account_symbol}")
        assert source_response.status_code == 200
        source = source_response.json()
        assert source["name"] == "AccountSchema"
        assert "class AccountSchema" in source["excerpt"]
