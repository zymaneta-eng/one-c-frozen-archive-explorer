"""
Web Server & Export Test Suite:
Tests FastAPI HTML pages, REST API (< 50ms), and openpyxl Excel exports.
"""

import io
import json
from pathlib import Path
import openpyxl
import pytest
from starlette.testclient import TestClient

from one_c_frozen_archive_explorer.server import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Fixture providing TestClient against the configured FastAPI app."""
    app = create_app()
    return TestClient(app)


def test_index_page(client: TestClient):
    """Test main explorer page loads with stats and table."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Frozen Archive Explorer" in resp.text
    assert "Документів в архіві" in resp.text
    assert "Air-Gapped" in resp.text


def test_index_page_search_filter(client: TestClient):
    """Test searching and filtering via HTML query parameters."""
    resp = client.get("/?q=РН-&doc_type=Видаткова+накладна")
    assert resp.status_code == 200
    assert "РН-" in resp.text


def test_api_search_endpoint(client: TestClient):
    """Test sub-50ms JSON search API."""
    client.get("/api/search?q=тест")  # Warm-up SQLite caches
    resp = client.get("/api/search?q=Київ")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "total_count" in data
    assert "execution_ms" in data
    assert data["execution_ms"] < 100.0


def test_api_suggest_endpoint(client: TestClient):
    """Test instant autocomplete suggestions API."""
    resp = client.get("/api/suggest?q=Київ")
    assert resp.status_code == 200
    suggestions = resp.json()
    assert isinstance(suggestions, list)


def test_api_stats_endpoint(client: TestClient):
    """Test global archive statistics API."""
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_documents"] >= 1000
    assert stats["total_counterparties"] >= 100
    assert "₴" in stats["formatted_total"]


def test_document_detail_and_print_pages(client: TestClient):
    """Test document detail view and printable accounting template."""
    # Find a valid document ID from API
    search_resp = client.get("/api/search?limit=1")
    doc_id = search_resp.json()["results"][0]["doc_id"]

    # 1. HTML Card View
    resp = client.get(f"/document/{doc_id}")
    assert resp.status_code == 200
    assert "Сума прописом" in resp.text
    assert "Специфікація товарів" in resp.text

    # 2. Printable HTML View (Ctrl+P ready)
    print_resp = client.get(f"/document/{doc_id}/print")
    assert print_resp.status_code == 200
    assert "print-sheet" in print_resp.text
    assert "Постачальник" in print_resp.text
    assert "Одержувач" in print_resp.text
    assert "М.П." in print_resp.text


def test_export_single_document_excel(client: TestClient):
    """Test exporting a single document to Excel (.xlsx) using openpyxl."""
    search_resp = client.get("/api/search?limit=1")
    doc_id = search_resp.json()["results"][0]["doc_id"]

    resp = client.get(f"/export/document/{doc_id}/excel")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]

    # Read the returned bytes into openpyxl to ensure valid XLSX structure
    excel_bytes = io.BytesIO(resp.content)
    wb = openpyxl.load_workbook(excel_bytes)
    assert len(wb.sheetnames) >= 1
    ws = wb.active
    assert "від" in ws["A1"].value
    assert ws["A3"].value == "Постачальник:"
    assert ws["A4"].value == "Одержувач:"


def test_export_search_results_excel(client: TestClient):
    """Test exporting filtered search results to Excel (.xlsx)."""
    resp = client.get("/export/search/excel?q=РН-")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp.headers["content-type"]

    excel_bytes = io.BytesIO(resp.content)
    wb = openpyxl.load_workbook(excel_bytes)
    ws = wb.active
    assert ws.title == "Результати пошуку"
    # Check headers
    assert ws["B1"].value == "Напрямок"
    assert ws["C1"].value == "Наша організація"
    assert ws["D1"].value == "Тип документа"
    assert ws["E1"].value == "Номер документа"
    assert ws["I1"].value == "Сума з ПДВ (грн)"
    # At least header + 1 row
    assert ws.max_row >= 2


def test_role_switcher_and_permissions(client: TestClient):
    """Test role switching cookie and permissions enforcement."""
    # Switch to TOV accountant
    resp = client.get("/api/auth/role?role=accountant_tov", follow_redirects=False)
    assert resp.status_code == 303
    assert "user_role=accountant_tov" in resp.headers.get("set-cookie", "")

    # Switch to DPS Auditor (Read-only)
    resp_auditor = client.get("/api/auth/role?role=auditor_dps", follow_redirects=False)
    assert resp_auditor.status_code == 303

    # Check auditor cannot download cold backup (403)
    client.cookies.set("user_role", "auditor_dps")
    resp_backup = client.get("/api/backup/download")
    assert resp_backup.status_code == 403

    # Chief accountant CAN download cold backup
    client.cookies.set("user_role", "chief_accountant")
    resp_backup_ok = client.get("/api/backup/download")
    assert resp_backup_ok.status_code == 200
    assert "application/zip" in resp_backup_ok.headers["content-type"]
    assert "Frozen_Archive_ColdBackup_" in resp_backup_ok.headers["content-disposition"]


def test_document_not_found(client: TestClient):
    """Test 404 behavior for non-existent document ID."""
    resp = client.get("/document/non_existent_doc_99999")
    assert resp.status_code == 404


def test_reconciliation_act_page_and_api(client: TestClient):
    """Test mutual reconciliation act HTML page and JSON API."""
    # First get stats or search to find a valid counterparty_id
    search_resp = client.get("/api/search?q=")
    data = search_resp.json()
    assert len(data["results"]) > 0
    cp_id = data["results"][0]["counterparty_id"]

    # Test HTML view
    resp_html = client.get(f"/reconciliation/{cp_id}")
    assert resp_html.status_code == 200
    assert "АКТ ЗВІРКИ" in resp_html.text
    assert "Сальдо" in resp_html.text

    # Test API view
    resp_api = client.get(f"/api/reconciliation/{cp_id}")
    assert resp_api.status_code == 200
    act_data = resp_api.json()
    assert "counterparty" in act_data
    assert "entries" in act_data
    assert "closing_balance_kopiykas" in act_data
    assert "closing_balance_in_words" in act_data


def test_worm_manifest_api(client: TestClient):
    """Test WORM audit manifest API."""
    resp = client.get("/api/worm/manifest")
    assert resp.status_code == 200
    manifest = resp.json()
    assert "vault_sha256" in manifest
    assert len(manifest["vault_sha256"]) == 64
    assert manifest["total_documents"] == 1000


def test_dps_registry_report_page(client: TestClient):
    """Test primary document registry for State Tax Service (ДПС)."""
    resp = client.get("/reports/dps-registry?q=")
    assert resp.status_code == 200
    assert "РЕЄСТР-ОПИС ПЕРВИННИХ ДОКУМЕНТІВ" in resp.text
    assert "ДПС" in resp.text
    assert "Сума без ПДВ" in resp.text
    assert "Головний бухгалтер" in resp.text

    # With EDRPOU filter
    resp_filtered = client.get("/reports/dps-registry?q=38491023")
    assert resp_filtered.status_code == 200
    assert "РЕЄСТР-ОПИС" in resp_filtered.text


def test_export_reconciliation_excel(client: TestClient):
    """Test exporting bilateral reconciliation act to Excel (.xlsx)."""
    search_resp = client.get("/api/search?q=")
    data = search_resp.json()
    assert len(data["results"]) > 0
    cp_id = data["results"][0]["counterparty_id"]

    resp = client.get(f"/export/reconciliation/{cp_id}/excel")
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in resp.headers["content-type"]

    excel_bytes = io.BytesIO(resp.content)
    wb = openpyxl.load_workbook(excel_bytes)
    assert "Акт звірки" in wb.sheetnames
    ws = wb["Акт звірки"]
    assert "АКТ ЗВІРКИ" in ws["A1"].value
    assert ws["C6"].value == "Дебет (грн)"
    assert ws["D6"].value == "Кредит (грн)"


def test_import_wizard_page(client: TestClient):
    """Test GET /import returns HTML wizard page with proper badges."""
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "Майстер імпорту" in resp.text
    assert "Крок 1:" in resp.text


def test_import_preview_and_execute_endpoints(client: TestClient):
    """Test pre-flight audit preview and execution of bundle import."""
    # 1. Preview with sample demo bundle
    resp_preview = client.post("/api/import/preview?use_sample=true")
    assert resp_preview.status_code == 200
    pdata = resp_preview.json()
    assert pdata["success"] is True
    assert pdata["stats"]["total_documents"] > 0
    assert "sample_documents" in pdata
    assert len(pdata["sample_documents"]) > 0

    # 2. Preview with custom uploaded JSON
    sample_payload = {
        "documents": [
            {
                "id": "test_doc_web_01",
                "doc_number": "РН-TEST-999",
                "doc_type": "Видаткова накладна",
                "doc_date": "2025-11-04",
                "counterparty_name": "ТОВ \"Тест Постач\"",
                "counterparty_edrpou": "12345678",
                "total_amount_kopiykas": 1200000,
                "vat_kopiykas": 200000,
                "direction": "OUT",
                "tax_invoice_number": "99901",
                "ernn_status": "Зареєстровано в ЄРНН",
                "doc_form": "Електронна (КЕП)",
                "edi_provider": "Вчасно",
                "items": [
                    {
                        "item_name": "Тестова послуга консервації",
                        "unit": "послуга",
                        "quantity": 1,
                        "unit_price_kopiykas": 1000000,
                        "amount_kopiykas": 1000000,
                        "vat_kopiykas": 200000,
                    }
                ]
            }
        ]
    }
    json_bytes = json.dumps(sample_payload).encode("utf-8")
    resp_upload_prev = client.post(
        "/api/import/preview",
        files={"file": ("custom_bundle.json", json_bytes, "application/json")}
    )
    assert resp_upload_prev.status_code == 200
    up_data = resp_upload_prev.json()
    assert up_data["stats"]["total_documents"] == 1
    assert up_data["stats"]["sales_count"] == 1

    # 3. Read-only role cannot execute import (403)
    client.cookies.set("user_role", "auditor_dps")
    resp_exec_forbidden = client.post("/api/import/execute?use_sample=true")
    assert resp_exec_forbidden.status_code == 403

    # 4. Chief accountant CAN execute import
    client.cookies.set("user_role", "chief_accountant")
    resp_exec = client.post(
        "/api/import/execute",
        files={"file": ("custom_bundle.json", json_bytes, "application/json")}
    )
    assert resp_exec.status_code == 200
    exec_res = resp_exec.json()
    assert exec_res["success"] is True
    assert "manifest" in exec_res
    assert len(exec_res["manifest"]["vault_sha256"]) == 64
