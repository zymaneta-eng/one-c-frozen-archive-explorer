"""
Web Server & Export Test Suite:
Tests FastAPI HTML pages, REST API (< 50ms), and openpyxl Excel exports.
"""

import io
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
    assert ws["B1"].value == "Наша організація"
    assert ws["C1"].value == "Тип документа"
    assert ws["D1"].value == "Номер документа"
    assert ws["H1"].value == "Сума з ПДВ (грн)"
    # At least header + 1 row
    assert ws.max_row >= 2


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
