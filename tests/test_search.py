"""
Search Engine Test Suite:
Validates sub-50ms hybrid FTS5 BM25 + DuckDB execution across EDRPOU, doc numbers, names, items.
"""

from pathlib import Path
import pytest

from one_c_frozen_archive_explorer.freeze_importer import FreezeImporter
from one_c_frozen_archive_explorer.search_engine import SearchEngine


@pytest.fixture(scope="module")
def populated_search_engine(tmp_path_factory) -> SearchEngine:
    """Fixture providing populated DuckDB + SQLite FTS5 engine."""
    tmp_path = tmp_path_factory.mktemp("search_test")
    db_file = tmp_path / "archive_vault.duckdb"
    idx_file = tmp_path / "archive_index.db"

    importer = FreezeImporter(db_path=db_file, index_path=idx_file)

    counterparties = [
        {
            "id": "cp_101",
            "edrpou": "38491023",
            "name": "ТОВ \"Поділля Софт\"",
            "short_name": "ТОВ \"Поділля Софт\"",
            "is_fop": False,
            "tax_system": "Загальна система",
            "iban": "UA213052990000026001234567891",
            "bank_name": "АТ ПриватБанк",
            "address": "м. Вінниця, вул. Соборна, 24",
            "phone": "+380671112233",
            "director": "Коваль В.І.",
        },
        {
            "id": "cp_102",
            "edrpou": "31298456",
            "name": "ТОВ \"Київ Буд Постач\"",
            "short_name": "ТОВ \"Київ Буд Постач\"",
            "is_fop": False,
            "tax_system": "Загальна система",
            "iban": "UA213004650000026001234567892",
            "bank_name": "АТ Ощадбанк",
            "address": "м. Київ, вул. Хрещатик, 22",
            "phone": "+380509998877",
            "director": "Бондар О.М.",
        },
        {
            "id": "cp_103",
            "edrpou": "2849102934",
            "name": "ФОП Лисенко Іван Васильович",
            "is_fop": True,
            "tax_system": "Єдиний податок 3 група",
            "iban": "UA213808050000026001234567893",
            "bank_name": "АТ Райффайзен Банк",
            "address": "м. Львів, вул. Наукова, 7Д",
            "phone": "+380635554433",
            "director": "Лисенко І.В.",
        },
    ]
    importer.import_counterparties_from_records(counterparties)

    documents = [
        {
            "id": "doc_101",
            "doc_number": "РН-00128",
            "doc_type": "Видаткова накладна",
            "doc_date": "2023-04-12",
            "counterparty_id": "cp_101",
            "counterparty_name": "ТОВ \"Поділля Софт\"",
            "counterparty_edrpou": "38491023",
            "total_amount_kopiykas": 1250000,  # 12 500.00 UAH
            "vat_kopiykas": 208333,
            "comment": "Поставка серверного обладнання Dell",
        },
        {
            "id": "doc_102",
            "doc_number": "АКТ-00055",
            "doc_type": "Акт виконаних робіт",
            "doc_date": "2024-06-18",
            "counterparty_id": "cp_102",
            "counterparty_name": "ТОВ \"Київ Буд Постач\"",
            "counterparty_edrpou": "31298456",
            "total_amount_kopiykas": 3400000,  # 34 000.00 UAH
            "vat_kopiykas": 566667,
            "comment": "Монтаж локальної мережі СКС у філії",
        },
        {
            "id": "doc_103",
            "doc_number": "СФ-00042",
            "doc_type": "Рахунок на оплату",
            "doc_date": "2024-09-01",
            "counterparty_id": "cp_103",
            "counterparty_name": "ФОП Лисенко Іван Васильович",
            "counterparty_edrpou": "2849102934",
            "total_amount_kopiykas": 800000,  # 8 000.00 UAH
            "vat_kopiykas": 0,
            "comment": "Оплата за юридичні консультації",
        },
    ]
    importer.import_documents_from_records(documents)

    items = [
        {
            "id": "it_101_1",
            "doc_id": "doc_101",
            "line_num": 1,
            "item_name": "Сервер Dell PowerEdge R650 1U",
            "unit": "шт",
            "quantity": 1.0,
            "unit_price_kopiykas": 1250000,
            "amount_kopiykas": 1250000,
            "vat_kopiykas": 208333,
        },
        {
            "id": "it_102_1",
            "doc_id": "doc_102",
            "line_num": 1,
            "item_name": "Монтажні роботи зі структурованої кабельної системи",
            "unit": "компл",
            "quantity": 1.0,
            "unit_price_kopiykas": 3400000,
            "amount_kopiykas": 3400000,
            "vat_kopiykas": 566667,
        },
        {
            "id": "it_103_1",
            "doc_id": "doc_103",
            "line_num": 1,
            "item_name": "Юридичні послуги супроводу договорів",
            "unit": "послуга",
            "quantity": 1.0,
            "unit_price_kopiykas": 800000,
            "amount_kopiykas": 800000,
            "vat_kopiykas": 0,
        },
    ]
    importer.import_items_from_records(items)
    importer.sync_fts_index()

    engine = SearchEngine(db_path=db_file, index_path=idx_file)
    engine.search("warmup")  # Warm-up SQLite caches
    return engine


def test_search_by_edrpou(populated_search_engine: SearchEngine):
    """Test instant search by Ukrainian 8-digit EDRPOU code."""
    results, total, ms = populated_search_engine.search(query="38491023")
    assert total == 1
    assert results[0].doc_number == "РН-00128"
    assert results[0].counterparty_name == "ТОВ \"Поділля Софт\""
    assert ms < 50.0


def test_search_by_fop_ipn(populated_search_engine: SearchEngine):
    """Test search by 10-digit IPN of an individual entrepreneur (ФОП)."""
    results, total, ms = populated_search_engine.search(query="2849102934")
    assert total == 1
    assert results[0].doc_number == "СФ-00042"
    assert "Лисенко" in results[0].counterparty_name
    assert ms < 50.0


def test_search_by_doc_number_with_hyphen(populated_search_engine: SearchEngine):
    """Test search by document number containing hyphen (РН-00128, СФ-00042)."""
    results, total, ms = populated_search_engine.search(query="РН-00128")
    assert total >= 1
    assert results[0].doc_number == "РН-00128"
    assert ms < 50.0

    results2, total2, ms2 = populated_search_engine.search(query="СФ-00042")
    assert total2 >= 1
    assert results2[0].doc_number == "СФ-00042"
    assert ms2 < 50.0


def test_search_by_item_name_and_comment(populated_search_engine: SearchEngine):
    """Test full-text search across item names and comments."""
    # By item: "Dell"
    results, total, ms = populated_search_engine.search(query="Dell")
    assert total == 1
    assert results[0].doc_number == "РН-00128"
    assert ms < 50.0

    # By comment word: "локальної"
    results2, total2, ms2 = populated_search_engine.search(query="локальної")
    assert total2 == 1
    assert results2[0].doc_number == "АКТ-00055"
    assert ms2 < 50.0


def test_search_filter_by_year_and_type(populated_search_engine: SearchEngine):
    """Test filtering by year and doc_type."""
    # Year 2023
    results, total, _ = populated_search_engine.search(query="", year=2023)
    assert total == 1
    assert results[0].doc_number == "РН-00128"

    # Year 2024
    results_24, total_24, _ = populated_search_engine.search(query="", year=2024)
    assert total_24 == 2

    # Filter by doc_type: "Акт виконаних робіт"
    res_akt, total_akt, _ = populated_search_engine.search(query="", doc_type="Акт виконаних робіт")
    assert total_akt == 1
    assert res_akt[0].doc_number == "АКТ-00055"


def test_document_details(populated_search_engine: SearchEngine):
    """Test loading full document details with counterparty and items."""
    doc = populated_search_engine.get_document_details("doc_101")
    assert doc is not None
    assert doc.doc_number == "РН-00128"
    assert doc.counterparty is not None
    assert doc.counterparty.edrpou == "38491023"
    assert len(doc.items) == 1
    assert doc.items[0].item_name == "Сервер Dell PowerEdge R650 1U"
    assert doc.total_amount_kopiykas == 1250000
    assert "гривень" in doc.total_in_words.lower()


def test_autocomplete_suggest(populated_search_engine: SearchEngine):
    """Test instant suggestion autocomplete."""
    suggestions = populated_search_engine.suggest(prefix="Поділля")
    assert len(suggestions) > 0
    assert "Поділля Софт" in suggestions[0]["text"]


def test_sub_50ms_performance_benchmark(populated_search_engine: SearchEngine):
    """Benchmark: 20 sequential searches must all complete well under 50ms."""
    queries = ["Поділля", "38491023", "РН-00128", "Київ", "кабельної", "2849102934", "Dell", "СФ-00042"]
    for q in queries:
        _, _, ms = populated_search_engine.search(query=q)
        assert ms < 50.0, f"Query '{q}' took {ms}ms, which exceeds 50ms requirement"


def test_reconciliation_act_debit_and_credit(tmp_path: Path):
    """Verify that shipments form DEBIT and payment instructions form CREDIT with exact balance."""
    db_file = tmp_path / "recon_vault.duckdb"
    idx_file = tmp_path / "recon_index.db"

    importer = FreezeImporter(db_path=db_file, index_path=idx_file)
    cp = [{
        "id": "cp_recon",
        "edrpou": "43981001",
        "name": "ТОВ \"Захід Трейд Постач\"",
    }]
    importer.import_counterparties_from_records(cp)

    docs = [
        # Shipment 1: RN (Debit) = 50 000.00 UAH
        {
            "id": "doc_r1",
            "doc_number": "РН-0101",
            "doc_type": "Видаткова накладна",
            "doc_date": "2024-03-10",
            "our_company_id": "org_01",
            "counterparty_id": "cp_recon",
            "counterparty_name": "ТОВ \"Захід Трейд Постач\"",
            "counterparty_edrpou": "43981001",
            "total_amount_kopiykas": 5000000,
            "status": "Проведено",
        },
        # Shipment 2: Akt (Debit) = 25 000.00 UAH
        {
            "id": "doc_r2",
            "doc_number": "АКТ-0102",
            "doc_type": "Акт виконаних робіт",
            "doc_date": "2024-03-15",
            "our_company_id": "org_01",
            "counterparty_id": "cp_recon",
            "counterparty_name": "ТОВ \"Захід Трейд Постач\"",
            "counterparty_edrpou": "43981001",
            "total_amount_kopiykas": 2500000,
            "status": "Проведено",
        },
        # Payment: Payment Instruction (Credit) = 60 000.00 UAH
        {
            "id": "doc_r3",
            "doc_number": "ПІ-0103",
            "doc_type": "Платіжна інструкція",
            "doc_date": "2024-03-20",
            "our_company_id": "org_01",
            "counterparty_id": "cp_recon",
            "counterparty_name": "ТОВ \"Захід Трейд Постач\"",
            "counterparty_edrpou": "43981001",
            "total_amount_kopiykas": 6000000,
            "status": "Проведено",
        },
    ]
    importer.import_documents_from_records(docs)
    importer.sync_fts_index()

    engine = SearchEngine(db_path=db_file, index_path=idx_file)
    recon = engine.get_reconciliation("43981001", our_company_id="org_01", start_date="2024-01-01", end_date="2024-12-31")
    assert recon is not None
    assert recon.counterparty.edrpou == "43981001"
    # Total Debit = 50 000 + 25 000 = 75 000.00 UAH (7 500 000 kop)
    assert recon.total_debit_kopiykas == 7500000
    # Total Credit = 60 000.00 UAH (6 000 000 kop)
    assert recon.total_credit_kopiykas == 6000000
    # Closing balance = 75 000 - 60 000 = 15 000.00 UAH (1 500 000 kop)
    assert recon.closing_balance_kopiykas == 1500000
    assert len(recon.entries) == 3
    # Check that payment entry has credit_kopiykas > 0 and debit == 0
    pay_entry = next(e for e in recon.entries if e.doc_number == "ПІ-0103")
    assert pay_entry.credit_kopiykas == 6000000
    assert pay_entry.debit_kopiykas == 0
    # Check that RN entry has debit > 0 and credit == 0
    rn_entry = next(e for e in recon.entries if e.doc_number == "РН-0101")
    assert rn_entry.debit_kopiykas == 5000000
    assert rn_entry.credit_kopiykas == 0

