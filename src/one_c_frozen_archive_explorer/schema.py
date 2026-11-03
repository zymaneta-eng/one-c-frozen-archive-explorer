"""
1C Frozen Archive Explorer - Schema & Financial Models
Strict integer-kopiyka storage, DuckDB DDL, SQLite FTS5 DDL, and Pydantic models.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# OUR ORGANIZATIONS (MULTI-ENTITY SUPPORT)
# ---------------------------------------------------------------------------

OUR_COMPANIES = [
    {
        "id": "org_01",
        "name": 'ТОВ "Ареонікс Діджитал"',
        "short_name": "Ареонікс Діджитал",
        "edrpou": "43981245",
        "tax_system": "Платник ПДВ на загальних підставах",
        "iban": "UA213052990000026001234567890",
        "bank_name": 'АТ КБ "ПриватБанк"',
        "address": "01001, м. Київ, вул. Хрещатик, 22, оф. 401",
        "director": "Коваленко О. В.",
    },
    {
        "id": "org_02",
        "name": 'ФОП "Ареонікс-Сервіс"',
        "short_name": 'ФОП "Ареонікс-Сервіс"',
        "edrpou": "3124598712",
        "tax_system": "Спрощена система (єдиний податок, 3 група, 5%)",
        "iban": "UA843004650000026009876543210",
        "bank_name": 'АТ "Ощадбанк"',
        "address": "79039, м. Львів, вул. Шевченка, 111А, оф. 15",
        "director": "Ареонікс Н. З.",
    },
]


# ---------------------------------------------------------------------------
# FINANCIAL ACCURACY UTILITIES (KOPIYKAS / CENTS - BIGINT)
# ---------------------------------------------------------------------------

def parse_kopiykas(val: Any) -> int:
    """
    Parses a value that is ALREADY expressed in integer kopiykas (or cents).
    E.g. 500000, "500000", "500000.0" -> 500000
    """
    if val is None or val == "":
        return 0
    if isinstance(val, int):
        return val
    try:
        s = str(val).strip().replace(" ", "").replace("\u00a0", "")
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def parse_uah_to_kopiykas(val: Any) -> int:
    """
    Strictly converts a UAH monetary amount to integer kopiykas (multiplies by 100).
    E.g.:
      "1234.56" -> 123456
      "1 234,56 ₴" -> 123456
      1000.5 -> 100050
      1000 -> 100000
    """
    if val is None or val == "":
        return 0

    s = str(val).strip()
    s = s.replace("₴", "").replace("грн", "").replace("UAH", "").replace(" ", "").replace("\u00a0", "")
    s = s.replace(",", ".")

    if not s:
        return 0

    try:
        dec = Decimal(s)
        kop = (dec * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(kop)
    except Exception:
        matches = re.findall(r"-?\d+(?:\.\d+)?", s)
        if matches:
            dec = Decimal(matches[0])
            return int((dec * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return 0


def parse_to_kopiykas(val: Any) -> int:
    """
    Converts numeric or string representation to integer kopiykas.
    If already an integer, preserves it.
    If float, string, or Decimal, converts UAH amount to kopiykas.
    """
    if val is None or val == "":
        return 0
    if isinstance(val, int):
        return val
    return parse_uah_to_kopiykas(val)


def format_kopiykas(amount_kopiykas: int | None, currency: str = "₴") -> str:
    """
    Formats kopiykas into Ukrainian standard accounting representation:
    100050 -> "1 000,50 ₴"
    -5000  -> "-50,00 ₴"
    """
    if amount_kopiykas is None:
        amount_kopiykas = 0
    
    is_negative = amount_kopiykas < 0
    abs_kop = abs(amount_kopiykas)
    hryvnias = abs_kop // 100
    kop = abs_kop % 100

    # Format hryvnias with thin/regular space for thousands
    hryvnias_str = f"{hryvnias:,}".replace(",", " ")
    sign = "-" if is_negative else ""
    curr = f" {currency}" if currency else ""
    return f"{sign}{hryvnias_str},{kop:02d}{curr}"


def kopiykas_to_uah_float(amount_kopiykas: int | None) -> float:
    """Converts integer kopiykas to float UAH for Excel / charts."""
    if amount_kopiykas is None:
        return 0.0
    return round(amount_kopiykas / 100.0, 2)


def kopiykas_to_uah_decimal(amount_kopiykas: int | None) -> Decimal:
    """Converts integer kopiykas to Decimal UAH."""
    if amount_kopiykas is None:
        return Decimal("0.00")
    return (Decimal(amount_kopiykas) / Decimal(100)).quantize(Decimal("0.01"))


def amount_in_words_ua(amount_kopiykas: int) -> str:
    """
    Converts kopiykas to Ukrainian words representation for official accounting documents.
    Example: 125035 -> "Одна тисяча двісті п'ятдесят гривень 35 копійок"
    """
    if amount_kopiykas < 0:
        return "Мінус " + amount_in_words_ua(-amount_kopiykas)
    
    uah = amount_kopiykas // 100
    kop = amount_kopiykas % 100

    units_m = ["", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"]
    units_f = ["", "одна", "дві", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"]
    teens = ["десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять",
             "п'ятнадцять", "шістнадцять", "сімнадцять", "вісімнадцять", "дев'ятнадцять"]
    tens = ["", "", "двадцять", "тридцять", "сорок", "п'ятдесят", "шістдесят", "сімдесят", "вісімдесят", "дев'яносто"]
    hundreds = ["", "сто", "двісті", "триста", "чотириста", "п'ятсот", "шістсот", "сімсот", "вісімсот", "дев'ятсот"]

    def _triplet(n: int, is_female: bool) -> tuple[str, int]:
        h = (n % 1000) // 100
        t = (n % 100) // 10
        u = n % 10
        parts = []
        if h > 0:
            parts.append(hundreds[h])
        last_digit = u
        if t == 1:
            parts.append(teens[u])
            last_digit = 0
        else:
            if t > 1:
                parts.append(tens[t])
            if u > 0:
                parts.append(units_f[u] if is_female else units_m[u])
        return " ".join(parts), last_digit

    if uah == 0:
        words = "Нуль гривень"
    else:
        # Scale: billions, millions, thousands, units
        groups = [
            (uah // 1_000_000_000, "мільярд", "мільярди", "мільярдів", False),
            ((uah % 1_000_000_000) // 1_000_000, "мільйон", "мільйони", "мільйонів", False),
            ((uah % 1_000_000) // 1_000, "тисяча", "тисячі", "тисяч", True),
            (uah % 1_000, "гривня", "гривні", "гривень", True),
        ]
        result = []
        for val, f1, f2, f5, is_fem in groups:
            if val > 0:
                t_str, last = _triplet(val, is_fem)
                if t_str:
                    result.append(t_str)
                # Form selection: 1 -> f1, 2..4 -> f2, 5..9,0,11..19 -> f5
                t_last_two = val % 100
                if 11 <= t_last_two <= 19:
                    form = f5
                elif last == 1:
                    form = f1
                elif 2 <= last <= 4:
                    form = f2
                else:
                    form = f5
                result.append(form)
            elif f1 == "гривня" and len(result) > 0 and not any("грив" in x for x in result):
                result.append("гривень")

        words = " ".join(result).capitalize()

    # Kopecks forms
    kop_last_two = kop % 100
    kop_last = kop % 10
    if 11 <= kop_last_two <= 19:
        kop_form = "копійок"
    elif kop_last == 1:
        kop_form = "копійка"
    elif 2 <= kop_last <= 4:
        kop_form = "копійки"
    else:
        kop_form = "копійок"

    return f"{words} {kop:02d} {kop_form}"


# ---------------------------------------------------------------------------
# DUCKDB & SQLITE DDL
# ---------------------------------------------------------------------------

DUCKDB_SCHEMA_SQL = """
-- Counterparties: legal entities & individual entrepreneurs (ТОВ, ФОП, ПрАТ, etc.)
CREATE TABLE IF NOT EXISTS counterparties (
    id VARCHAR PRIMARY KEY,
    edrpou VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    short_name VARCHAR,
    is_fop BOOLEAN DEFAULT FALSE,
    tax_system VARCHAR DEFAULT 'Загальна система',
    iban VARCHAR,
    bank_name VARCHAR,
    address VARCHAR,
    phone VARCHAR,
    email VARCHAR,
    director VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_counterparty_edrpou ON counterparties (edrpou);
CREATE INDEX IF NOT EXISTS idx_counterparty_name ON counterparties (name);

-- 1C Primary Accounting Documents (Видаткові накладні, Акти робіт, Рахунки)
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR PRIMARY KEY,
    doc_number VARCHAR NOT NULL,
    doc_type VARCHAR NOT NULL,
    doc_date DATE NOT NULL,
    our_company_id VARCHAR DEFAULT 'org_01',
    our_company_name VARCHAR DEFAULT 'ТОВ "Ареонікс Діджитал"',
    our_company_edrpou VARCHAR DEFAULT '43981245',
    counterparty_id VARCHAR NOT NULL,
    counterparty_name VARCHAR NOT NULL,
    counterparty_edrpou VARCHAR NOT NULL,
    total_amount_kopiykas BIGINT NOT NULL,
    vat_kopiykas BIGINT NOT NULL DEFAULT 0,
    currency VARCHAR DEFAULT 'UAH',
    status VARCHAR DEFAULT 'Проведено',
    contract_number VARCHAR,
    comment VARCHAR,
    year INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_file VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_doc_number ON documents (doc_number);
CREATE INDEX IF NOT EXISTS idx_doc_date ON documents (doc_date);
CREATE INDEX IF NOT EXISTS idx_doc_type ON documents (doc_type);
CREATE INDEX IF NOT EXISTS idx_doc_year ON documents (year);
CREATE INDEX IF NOT EXISTS idx_doc_counterparty ON documents (counterparty_id);
CREATE INDEX IF NOT EXISTS idx_doc_our_company ON documents (our_company_id);

-- Line items for each document
CREATE TABLE IF NOT EXISTS document_items (
    id VARCHAR PRIMARY KEY,
    doc_id VARCHAR NOT NULL,
    line_num INTEGER NOT NULL,
    item_name VARCHAR NOT NULL,
    sku VARCHAR,
    unit VARCHAR DEFAULT 'шт',
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price_kopiykas BIGINT NOT NULL,
    amount_kopiykas BIGINT NOT NULL,
    vat_kopiykas BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_items_doc_id ON document_items (doc_id);
"""

SQLITE_FTS_SCHEMA_SQL = """
-- SQLite FTS5 Full-Text Search Table with Ukrainian tokenization
CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts USING fts5(
    doc_id UNINDEXED,
    doc_number,
    doc_type,
    counterparty_name,
    counterparty_edrpou,
    comment,
    items_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


# ---------------------------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------------------------

class CounterpartyModel(BaseModel):
    id: str
    edrpou: str
    name: str
    short_name: Optional[str] = None
    is_fop: bool = False
    tax_system: Optional[str] = "Платник ПДВ на загальних підставах"
    iban: Optional[str] = None
    bank_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    director: Optional[str] = None


class DocumentItemModel(BaseModel):
    id: str
    doc_id: str
    line_num: int
    item_name: str
    sku: Optional[str] = None
    unit: str = "шт"
    quantity: float
    unit_price_kopiykas: int
    amount_kopiykas: int
    vat_kopiykas: int = 0

    @property
    def formatted_unit_price(self) -> str:
        return format_kopiykas(self.unit_price_kopiykas)

    @property
    def formatted_amount(self) -> str:
        return format_kopiykas(self.amount_kopiykas)

    @property
    def formatted_vat(self) -> str:
        return format_kopiykas(self.vat_kopiykas)


class DocumentHeaderModel(BaseModel):
    id: str
    doc_number: str
    doc_type: str
    doc_date: str
    our_company_id: str = "org_01"
    our_company_name: str = 'ТОВ "Ареонікс Діджитал"'
    our_company_edrpou: str = "43981245"
    counterparty_id: str
    counterparty_name: str
    counterparty_edrpou: str
    total_amount_kopiykas: int
    vat_kopiykas: int = 0
    currency: str = "UAH"
    status: str = "Проведено"
    contract_number: Optional[str] = None
    comment: Optional[str] = None
    year: int
    source_file: Optional[str] = None

    @computed_field
    @property
    def formatted_total(self) -> str:
        return format_kopiykas(self.total_amount_kopiykas)

    @computed_field
    @property
    def formatted_vat(self) -> str:
        return format_kopiykas(self.vat_kopiykas)


class DocumentDetailModel(DocumentHeaderModel):
    counterparty: Optional[CounterpartyModel] = None
    items: List[DocumentItemModel] = Field(default_factory=list)

    @computed_field
    @property
    def total_in_words(self) -> str:
        return amount_in_words_ua(self.total_amount_kopiykas)

    @computed_field
    @property
    def amount_without_vat_kopiykas(self) -> int:
        return self.total_amount_kopiykas - self.vat_kopiykas

    @computed_field
    @property
    def formatted_without_vat(self) -> str:
        return format_kopiykas(self.amount_without_vat_kopiykas)


class SearchResultModel(BaseModel):
    doc_id: str
    doc_number: str
    doc_type: str
    doc_date: str
    our_company_id: str = "org_01"
    our_company_name: str = 'ТОВ "Ареонікс Діджитал"'
    our_company_edrpou: str = "43981245"
    counterparty_id: Optional[str] = None
    counterparty_name: str
    counterparty_edrpou: str
    total_amount_kopiykas: int
    formatted_total: str
    comment: Optional[str] = None
    snippet: Optional[str] = None
    rank: float = 0.0


class SearchQueryModel(BaseModel):
    query: str = ""
    doc_type: Optional[str] = None
    year: Optional[int] = None
    our_company_id: Optional[str] = None
    limit: int = 50
    offset: int = 0


class ArchiveStatsModel(BaseModel):
    total_documents: int
    total_counterparties: int
    total_items: int
    total_amount_kopiykas: int
    formatted_total: str
    years: List[int]
    doc_types: List[str]
    our_companies: List[Dict[str, str]] = Field(default_factory=list)
    selected_org: Optional[str] = None
    parquet_storage_path: Optional[str] = None


class ReconciliationEntryModel(BaseModel):
    date: str
    doc_number: str
    doc_type: str
    debit_kopiykas: int = 0
    credit_kopiykas: int = 0
    debit_formatted: str = "0,00 ₴"
    credit_formatted: str = "0,00 ₴"


class ReconciliationReportModel(BaseModel):
    counterparty: CounterpartyModel
    our_company_id: str
    our_company_name: str
    our_company_edrpou: str
    start_date: str
    end_date: str
    opening_balance_kopiykas: int = 0
    closing_balance_kopiykas: int = 0
    total_debit_kopiykas: int = 0
    total_credit_kopiykas: int = 0
    opening_balance_formatted: str
    closing_balance_formatted: str
    total_debit_formatted: str
    total_credit_formatted: str
    closing_balance_in_words: str
    entries: List[ReconciliationEntryModel] = Field(default_factory=list)


class WormManifestModel(BaseModel):
    vault_sha256: str
    frozen_at: str
    total_documents: int
    total_items: int
    total_counterparties: int
    total_turnover_kopiykas: int
    formatted_turnover: str
    min_doc_date: str
    max_doc_date: str
    statute_reference: str = "п. 44.3 ст. 44 ПКУ (збереження первинних документів не менше 1825 днів)"
    integrity_status: str = "✅ Цілісність перевірена (SHA-256 Bit-Level Verified)"
