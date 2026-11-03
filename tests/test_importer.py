"""
Unit & Integration tests for FreezeImporter & Financial Precision (Kopiykas).
"""

from decimal import Decimal
from pathlib import Path
import duckdb
import pytest

from one_c_frozen_archive_explorer.freeze_importer import FreezeImporter
from one_c_frozen_archive_explorer.schema import (
    amount_in_words_ua,
    format_kopiykas,
    kopiykas_to_uah_decimal,
    kopiykas_to_uah_float,
    parse_to_kopiykas,
)


def test_financial_kopiykas_accuracy():
    """Verify strictly integer kopiyka parsing and formatting with zero float drift."""
    # Test strings with various formats
    assert parse_to_kopiykas("1000.50") == 100050
    assert parse_to_kopiykas("1000.5") == 100050
    assert parse_to_kopiykas("1 234,56 ₴") == 123456
    assert parse_to_kopiykas("1234,56 грн") == 123456
    assert parse_to_kopiykas(Decimal("4500.99")) == 450099
    assert parse_to_kopiykas(100) == 100  # already integer kopiykas
    assert parse_to_kopiykas(None) == 0
    assert parse_to_kopiykas("") == 0

    # Conversions
    assert kopiykas_to_uah_float(100050) == 1000.50
    assert kopiykas_to_uah_decimal(100050) == Decimal("1000.50")

    # Ukrainian formatting
    formatted = format_kopiykas(100050)
    assert "1" in formatted and "000,50" in formatted and "₴" in formatted

    # Ukrainian words representation
    words = amount_in_words_ua(125035)
    assert "тисяча" in words.lower()
    assert "гривень" in words.lower()
    assert "35 копійок" in words.lower()


def test_importer_records_and_parquet(tmp_path: Path):
    """Test full ETL cycle: DuckDB tables, SQLite FTS, and Snappy Parquet export."""
    db_file = tmp_path / "test_vault.duckdb"
    idx_file = tmp_path / "test_index.db"
    parquet_dir = tmp_path / "parquets"

    importer = FreezeImporter(db_path=db_file, index_path=idx_file, parquet_dir=parquet_dir)

    # 1. Import counterparties
    counterparties = [
        {
            "id": "cp_001",
            "edrpou": "38291045",
            "name": "ТОВ \"Дніпро-Логістик\"",
            "short_name": "ТОВ \"Дніпро-Логістик\"",
            "is_fop": False,
            "tax_system": "Загальна система",
            "iban": "UA213052990000026001234567890",
            "bank_name": "АТ КБ ПриватБанк",
            "address": "м. Дніпро, вул. Січових Стрільців, 14",
            "phone": "+380501234567",
            "director": "Коваленко О.В.",
        },
        {
            "id": "cp_002",
            "edrpou": "2984512345",
            "name": "ФОП Шевченко Тарас Григорович",
            "is_fop": True,
            "tax_system": "Єдиний податок 3 група",
            "iban": "UA213004650000026009876543210",
            "bank_name": "АТ Ощадбанк",
            "address": "м. Київ, вул. Хрещатик, 22",
            "phone": "+380679876543",
            "director": "Шевченко Т.Г.",
        },
    ]
    cp_count = importer.import_counterparties_from_records(counterparties)
    assert cp_count == 2

    # 2. Import documents
    documents = [
        {
            "id": "doc_001",
            "doc_number": "РН-00042",
            "doc_type": "Видаткова накладна",
            "doc_date": "2023-05-15",
            "counterparty_id": "cp_001",
            "counterparty_name": "ТОВ \"Дніпро-Логістик\"",
            "counterparty_edrpou": "38291045",
            "total_amount_kopiykas": 500000,  # 5 000.00 UAH
            "vat_kopiykas": 83333,
            "currency": "UAH",
            "status": "Проведено",
            "contract_number": "12/23-П",
            "comment": "Поставка комутатора Cisco",
        },
        {
            "id": "doc_002",
            "doc_number": "АКТ-00018",
            "doc_type": "Акт виконаних робіт",
            "doc_date": "2024-02-20",
            "counterparty_id": "cp_002",
            "counterparty_name": "ФОП Шевченко Тарас Григорович",
            "counterparty_edrpou": "2984512345",
            "total_amount_kopiykas": 1500000,  # 15 000.00 UAH
            "vat_kopiykas": 0,
            "currency": "UAH",
            "status": "Проведено",
            "contract_number": "05/24-У",
            "comment": "Послуги IT аудиту",
        },
    ]
    doc_count = importer.import_documents_from_records(documents)
    assert doc_count == 2

    # 3. Import line items
    items = [
        {
            "id": "item_001_1",
            "doc_id": "doc_001",
            "line_num": 1,
            "item_name": "Комутатор керований Cisco CBS350",
            "sku": "АРТ-10293",
            "unit": "шт",
            "quantity": 1.0,
            "unit_price_kopiykas": 500000,
            "amount_kopiykas": 500000,
            "vat_kopiykas": 83333,
        },
        {
            "id": "item_002_1",
            "doc_id": "doc_002",
            "line_num": 1,
            "item_name": "Аудит інформаційної безпеки та серверів",
            "sku": "АРТ-88210",
            "unit": "послуга",
            "quantity": 1.0,
            "unit_price_kopiykas": 1500000,
            "amount_kopiykas": 1500000,
            "vat_kopiykas": 0,
        },
    ]
    items_count = importer.import_items_from_records(items)
    assert items_count == 2

    # 4. Sync SQLite FTS5 index
    fts_rows = importer.sync_fts_index()
    assert fts_rows == 2

    # 5. Export Snappy Parquet snapshots
    parquet_paths = importer.export_parquet_snapshots()
    assert "documents" in parquet_paths
    assert Path(parquet_paths["documents"]).exists()
    assert Path(parquet_paths["counterparties"]).exists()
    assert Path(parquet_paths["document_items"]).exists()

    # 6. Verify DuckDB can directly query the Snappy Parquet file
    con = duckdb.connect()
    parquet_doc_path = str(parquet_paths["documents"]).replace("\\", "/")
    pq_count = con.execute(f"SELECT count(*) FROM read_parquet('{parquet_doc_path}')").fetchone()[0]
    assert pq_count == 2
    con.close()

    # 7. Check storage stats
    stats = importer.get_storage_stats()
    assert stats["documents_count"] == 2
    assert stats["counterparties_count"] == 2
    assert stats["items_count"] == 2
    assert stats["total_amount_kopiykas"] == 2000000  # 20 000.00 UAH
    assert stats["parquet_size_bytes"] > 0


def test_universal_date_parser():
    """Verify universal date parser supporting UA/1C, ISO, slash, and timestamp formats."""
    from one_c_frozen_archive_explorer.freeze_importer import parse_date_to_iso

    # Standard Ukrainian / 1C format (DD.MM.YYYY)
    assert parse_date_to_iso("15.05.2024") == "2024-05-15"
    assert parse_date_to_iso("01.12.2023") == "2023-12-01"

    # With time
    assert parse_date_to_iso("15.05.2024 14:30:00") == "2024-05-15"
    assert parse_date_to_iso("2024-05-15T10:00:00Z") == "2024-05-15"

    # Slashes and dashes (DD/MM/YYYY and DD-MM-YYYY)
    assert parse_date_to_iso("20/08/2022") == "2022-08-20"
    assert parse_date_to_iso("05-11-2025") == "2025-11-05"

    # ISO format (YYYY-MM-DD)
    assert parse_date_to_iso("2024-01-31") == "2024-01-31"

    # Fallbacks / empty
    assert parse_date_to_iso(None) == "2024-01-01"
    assert parse_date_to_iso("") == "2024-01-01"


def test_smart_column_resolver_and_elastic_mapping(tmp_path: Path):
    """Verify multilingual 1C column mapping (RU/UA/EN) automatically resolves into canonical schema."""
    from one_c_frozen_archive_explorer.freeze_importer import (
        normalize_column_name,
        normalize_record,
        FreezeImporter,
    )

    # Test individual header resolvers
    assert normalize_column_name("Код по ЕДРПОУ") == "edrpou"
    assert normalize_column_name("Код_за_ЄДРПОУ") == "edrpou"
    assert normalize_column_name("Наименование") == "name"
    assert normalize_column_name("Номер документа") == "doc_number"
    assert normalize_column_name("Дата документа") == "doc_date"
    assert normalize_column_name("Сумма с НДС") == "total_amount"
    assert normalize_column_name("Сумма_НДС") == "vat_amount"
    assert normalize_column_name("Номенклатура") == "item_name"
    assert normalize_column_name("Кол-во") == "quantity"
    assert normalize_column_name("Цена") == "unit_price"

    # Test ETL import with Russian and Ukrainian raw headers
    db_file = tmp_path / "resolver_vault.duckdb"
    idx_file = tmp_path / "resolver_index.db"
    importer = FreezeImporter(db_path=db_file, index_path=idx_file)

    # Counterparty with Russian headers
    raw_cp = [{
        "Код_ЕДРПОУ": "44185636",
        "Наименование": "ПП \"Крок у Майбутнє\"",
        "Юридический_адрес": "м. Дніпро, вул. Набережна, 32",
        "ИНН": "441856361234",
    }]
    importer.import_counterparties_from_records(raw_cp)

    # Documents with 1C Russian headers and date in DD.MM.YYYY
    raw_docs = [
        {
            "Номер_документа": "РН-777",
            "Вид_документа": "Видаткова накладна",
            "Дата": "20.12.2024",
            "Контрагент": "ПП \"Крок у Майбутнє\"",
            "ЕДРПОУ_контрагента": "44185636",
            "Сумма_с_НДС": "12000.50",
            "Сумма_НДС": "2000.08",
        },
        {
            "Номер_документа": "ПІ-888",
            "Вид_документа": "Платіжна інструкція",
            "Дата": "25.12.2024",
            "Контрагент": "ПП \"Крок у Майбутнє\"",
            "ЕДРПОУ_контрагента": "44185636",
            "Сумма": "12000.50",
            "Сумма_НДС": "2000.08",
        },
    ]
    importer.import_documents_from_records(raw_docs)

    # Line items with 1C Russian headers
    raw_items = [
        {
            "Doc_ID": "doc_РН-777_2024-12-20",
            "Номер_строки": "1",
            "Номенклатура": "Серверний модуль пам'яті 32GB",
            "Ед_изм": "шт",
            "Количество": "2",
            "Цена": "6000.25",
            "Сумма_строки": "12000.50",
        }
    ]
    importer.import_items_from_records(raw_items)

    # Verify DuckDB contents
    con = importer.get_duckdb_connection(read_only=True)
    cp_row = con.execute("SELECT edrpou, name FROM counterparties WHERE edrpou = '44185636'").fetchone()
    assert cp_row is not None
    assert cp_row[0] == "44185636"
    assert "Крок у Майбутнє" in cp_row[1]

    doc_rows = con.execute("SELECT doc_number, doc_type, strftime(doc_date, '%Y-%m-%d'), total_amount_kopiykas FROM documents ORDER BY doc_number").fetchall()
    assert len(doc_rows) == 2
    # Verify exact kopiykas parsing: 12000.50 -> 1200050 kopiykas
    assert doc_rows[0][0] == "ПІ-888" and doc_rows[0][1] == "Платіжна інструкція" and doc_rows[0][2] == "2024-12-25" and doc_rows[0][3] == 1200050
    assert doc_rows[1][0] == "РН-777" and doc_rows[1][1] == "Видаткова накладна" and doc_rows[1][2] == "2024-12-20" and doc_rows[1][3] == 1200050
    con.close()

