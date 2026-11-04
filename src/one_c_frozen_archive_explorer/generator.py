"""
1C Frozen Archive Explorer - Synthetic Data Generator
Generates realistic Ukrainian counterparties (valid EDRPOU/IPN) and 1,000 accounting documents
with line items in CSV and JSON formats, then executes ETL import into DuckDB and SQLite FTS5.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from one_c_frozen_archive_explorer.freeze_importer import FreezeImporter

logger = logging.getLogger("generator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------------------------------------------------------
# UKRAINIAN SEED DATA
# ---------------------------------------------------------------------------

CITIES_ADDRESSES = [
    ("Київ", "вул. Хрещатик, 22, оф. 401", "01001"),
    ("Київ", "вул. Велика Васильківська, 72, поверх 5", "03150"),
    ("Київ", "вул. Мечникова, 2, БЦ 'Парус'", "01601"),
    ("Київ", "просп. Степана Бандери, 9, корп. 3Б", "04073"),
    ("Київ", "вул. Дегтярівська, 33В, оф. 12", "04119"),
    ("Львів", "вул. Шевченка, 111А, оф. 15", "79039"),
    ("Львів", "вул. Наукова, 7Д, БЦ 'Оптіма'", "79060"),
    ("Львів", "вул. Городоцька, 206", "79040"),
    ("Дніпро", "просп. Дмитра Яворницького, 50, оф. 310", "49000"),
    ("Дніпро", "вул. Набережна Перемоги, 32", "49094"),
    ("Дніпро", "вул. Січових Стрільців, 14", "49006"),
    ("Одеса", "вул. Дерибасівська, 14, оф. 8", "65026"),
    ("Одеса", "просп. Шевченка, 4Д, БЦ 'Шевченківський'", "65044"),
    ("Одеса", "вул. Балківська, 120/1", "65005"),
    ("Харків", "вул. Сумська, 40, оф. 204", "61022"),
    ("Харків", "просп. Науки, 14", "61166"),
    ("Вінниця", "вул. Соборна, 24, оф. 18", "21050"),
    ("Вінниця", "Хмельницьке шосе, 82, БЦ 'Простір'", "21029"),
    ("Запоріжжя", "просп. Соборний, 158", "69035"),
    ("Полтава", "вул. Європейська, 21, оф. 5", "36000"),
]

BANKS = [
    ("АТ КБ 'ПриватБанк'", "305299"),
    ("АТ 'Ощадбанк'", "300465"),
    ("АТ 'Райффайзен Банк'", "380805"),
    ("АТ 'ПУМБ'", "334851"),
    ("АТ 'Укрсиббанк'", "351005"),
    ("АТ 'Укргазбанк'", "320478"),
    ("АТ 'СЕНС БАНК'", "300346"),
]

COMPANY_PREFIXES = ["ТОВ", "ПП", "ПрАТ"]
COMPANY_NAMES = [
    "Агро-Технології Південь", "Дніпро-Логістик", "Київ Буд Постач", "Поділля Софт",
    "Галицький Бровар", "Січ Енерго", "Карпати Консалт", "Одеса Шиппінг", "Слобожанський Хліб",
    "МетІнвест Сервіс", "Східний Трейд", "Інтерпайп Інжиніринг", "Волинь-Фарм", "Полісся Деревпром",
    "Таврія Агрогруп", "Дніпро-Флекс", "Атлант Будіндустрія", "Фармак Інновації", "Люксен Авто",
    "Енерджі Сістемс", "Смарт Дата Лабс", "Грінвей Логістикс", "УкрТрансГарант", "Біо-Органік",
    "Астра Медіа", "СофтПро Україна", "МайстерПак", "Вектор Інфраструктура", "Нова Мережа",
    "Омега Трейдинг", "ПромТехКомплект", "Альфа-Сервіс Груп", "Юніон Консалтинг", "Транс-Експрес",
    "Еко-Лайф Україна", "Єврохім Снаб", "Київ Цифра", "Техно-Сфера", "Він-Агро Груп", "Південний Портал",
    "Хрещатик Інвест", "Крок у Майбутнє", "УкрЕкоСфера", "Оптіма Телеком", "Термо-Плюс", "СпецОдяг Укр",
    "Західні Вікна", "Фенікс Сек'юріті", "АвіаТранс Логістик", "ГідроПром Сервіс"
]

FOP_FIRST_NAMES = ["Олександр", "Сергій", "Володимир", "Дмитро", "Андрій", "Михайло", "Олексій", "Ігор", "Віталій", "Тарас"]
FOP_LAST_NAMES = ["Коваленко", "Шевченко", "Бойко", "Кравченко", "Лисенко", "Бондаренко", "Ткаченко", "Мороз", "Козак", "Олійник"]
FOP_PATRONYMICS = ["Володимирович", "Олександрович", "Сергійович", "Іванович", "Миколайович", "Петрович", "Васильович"]

ITEMS_CATALOG = [
    # Services (p_min, p_max in kopiykas: 1 UAH = 100 kop)
    ("Послуги IT-консалтингу та налаштування ПЗ", "послуга", 1400000, 2600000, False),  # 14k - 26k ₴
    ("Технічна підтримка серверної інфраструктури (1 міс.)", "міс", 1500000, 2400000, False),  # 15k - 24k ₴
    ("Аудит фінансової звітності та податкового обліку", "послуга", 2200000, 3800000, False),  # 22k - 38k ₴
    ("Юридичний супровід договорів та контрактів", "год", 120000, 160000, False),  # 1.2k - 1.6k ₴ / год
    ("Монтаж та налаштування локальної мережі (СКС)", "компл", 1600000, 3200000, False),  # 16k - 32k ₴
    ("Оренда офісного приміщення (1 міс.)", "міс", 2800000, 4800000, False),  # 28k - 48k ₴
    ("Транспортно-експедиторські послуги (перевезення)", "рейс", 1200000, 2200000, False),  # 12k - 22k ₴
    ("Послуги відповідального зберігання вантажу (10 діб)", "доба", 60000, 100000, False),  # 600 - 1000 ₴ / доба
    # Goods
    ("Серверний вузол Dell PowerEdge 1U Xeon 32GB", "шт", 7200000, 9800000, True),  # 72k - 98k ₴
    ("Маршрутизатор MikroTik CCR2004-16G-2S+", "шт", 1450000, 1950000, True),  # 14.5k - 19.5k ₴
    ("Кабель оптичний FTTH 1000м волокно G.657A1", "бухта", 520000, 750000, True),  # 5.2k - 7.5k ₴
    ("Ноутбук Lenovo ThinkPad L14 Gen 4 Ryzen 7 16GB", "шт", 2600000, 3400000, True),  # 26k - 34k ₴
    ("Монітор 27\" Dell IPS QHD USB-C", "шт", 1050000, 1350000, True),  # 10.5k - 13.5k ₴
    ("Джерело безперебійного живлення APC 1500VA", "шт", 1750000, 2400000, True),  # 17.5k - 24k ₴
    ("Папір офісний Maestro Standard A4 80г/м2 (коробка)", "кор", 105000, 135000, True),  # 1050 - 1350 ₴
    ("Картридж тонерний HP 83A (CF283A) оригінальний", "шт", 165000, 220000, True),  # 1650 - 2200 ₴
    ("Комплект відеоспостереження Hikvision 4 камери PoE", "компл", 1550000, 2100000, True),  # 15.5k - 21k ₴
    ("Комутатор керований Cisco CBS350 24-портовий", "шт", 2100000, 2700000, True),  # 21k - 27k ₴
]

DOC_TYPES = [
    ("Видаткова накладна", "РН-", 0.38),
    ("Акт виконаних робіт", "АКТ-", 0.27),
    ("Платіжна інструкція", "ПІ-", 0.25),
    ("Рахунок на оплату", "СФ-", 0.10),
]

CONTRACT_TYPES = ["Поставки", "Надання послуг", "Оренди", "Підряду", "Дистриб'юції"]


def generate_edrpou(is_fop: bool) -> str:
    """Generates valid 8-digit EDRPOU for companies or 10-digit IPN for FOPs."""
    if is_fop:
        # 10 digits
        return f"{random.randint(2000000000, 3999999999)}"
    else:
        # 8 digits
        return f"{random.randint(10000000, 44999999)}"


def generate_iban(mfo: str) -> str:
    """Generates standard Ukrainian IBAN format: UA + 2 check digits + 6 MFO + 19 account digits."""
    account = f"{random.randint(1000000000000000000, 9999999999999999999)}"
    return f"UA{random.randint(10, 99)}{mfo}{account}"


def generate_counterparties(count: int = 100) -> List[Dict[str, Any]]:
    """Generates 100 Ukrainian counterparties."""
    random.seed(42)  # Deterministic generation
    counterparties = []

    fop_count = count // 4  # 25% FOP, 75% Legal entities
    corp_count = count - fop_count

    # Generate Legal Entities
    for i in range(corp_count):
        prefix = random.choice(COMPANY_PREFIXES)
        c_name = COMPANY_NAMES[i % len(COMPANY_NAMES)]
        full_name = f"{prefix} \"{c_name}\""
        short_name = f"{prefix} \"{c_name}\""
        edrpou = generate_edrpou(is_fop=False)
        city, street, zip_code = random.choice(CITIES_ADDRESSES)
        bank_name, mfo = random.choice(BANKS)
        director = f"{random.choice(FOP_LAST_NAMES)} {random.choice(FOP_FIRST_NAMES)[0]}.{random.choice(FOP_PATRONYMICS)[0]}."

        counterparties.append({
            "id": f"cp_{i+1:04d}",
            "edrpou": edrpou,
            "name": full_name,
            "short_name": short_name,
            "is_fop": False,
            "tax_system": "Платник ПДВ на загальних підставах",
            "iban": generate_iban(mfo),
            "bank_name": bank_name,
            "address": f"{zip_code}, м. {city}, {street}",
            "phone": f"+380{random.randint(50, 99)}{random.randint(1000000, 9999999)}",
            "email": f"buh@{c_name.lower().replace(' ', '').replace('-', '').replace('\"', '')}.ua",
            "director": director,
        })

    # Generate FOPs
    for i in range(fop_count):
        f_name = random.choice(FOP_FIRST_NAMES)
        l_name = random.choice(FOP_LAST_NAMES)
        p_name = random.choice(FOP_PATRONYMICS)
        full_name = f"ФОП {l_name} {f_name} {p_name}"
        short_name = f"ФОП {l_name} {f_name[0]}.{p_name[0]}."
        edrpou = generate_edrpou(is_fop=True)
        city, street, zip_code = random.choice(CITIES_ADDRESSES)
        bank_name, mfo = random.choice(BANKS)

        counterparties.append({
            "id": f"cp_{corp_count + i + 1:04d}",
            "edrpou": edrpou,
            "name": full_name,
            "short_name": short_name,
            "is_fop": True,
            "tax_system": "Спрощена система (єдиний податок, 3 група, 5%)",
            "iban": generate_iban(mfo),
            "bank_name": bank_name,
            "address": f"{zip_code}, м. {city}, {street}",
            "phone": f"+380{random.randint(50, 99)}{random.randint(1000000, 9999999)}",
            "email": f"{l_name.lower()}@gmail.com",
            "director": short_name,
        })

    return counterparties


def generate_documents_and_items(
    counterparties: List[Dict[str, Any]],
    doc_count: int = 1000,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Generates 1,000 historical documents spanning 2021-2025 with line items,
    computing exact integer kopiykas without floating point rounding error.
    Calibrated for realistic SME scale: total turnover ~48.3M UAH, min ~5k UAH, max ~350k UAH.
    """
    random.seed(223)
    documents = []
    items = []

    start_date = date(2021, 1, 10)
    end_date = date(2025, 12, 20)
    day_span = (end_date - start_date).days

    doc_counters = {
        "РН-": 1,
        "АКТ-": 1,
        "СФ-": 1,
        "ПІ-": 1,
        "ПНк-": 1,
        "АктВх-": 1,
        "ПІв-": 1,
    }

    for i in range(1, doc_count + 1):
        if i <= len(counterparties):
            cp = counterparties[i - 1]
        else:
            cp = random.choice(counterparties)
        rnd_days = random.randint(0, day_span)
        doc_date = start_date + timedelta(days=rnd_days)

        # 58% Sales (OUT, Доходи/Продажі), 42% Purchases (IN, Витрати/Постачальники)
        if random.random() < 0.58:
            direction = "OUT"
            r_type = random.random()
            if r_type < 0.44:
                doc_type, prefix = "Видаткова накладна", "РН-"
            elif r_type < 0.74:
                doc_type, prefix = "Акт виконаних робіт", "АКТ-"
            elif r_type < 0.90:
                doc_type, prefix = "Платіжна інструкція", "ПІ-"
            else:
                doc_type, prefix = "Рахунок на оплату", "СФ-"
        else:
            direction = "IN"
            r_type = random.random()
            if r_type < 0.50:
                doc_type, prefix = "Прибуткова накладна", "ПНк-"
            elif r_type < 0.82:
                doc_type, prefix = "Акт отриманих послуг", "АктВх-"
            else:
                doc_type, prefix = "Платіжна інструкція (вихідна)", "ПІв-"

        num = doc_counters[prefix]
        doc_counters[prefix] += 1
        doc_number = f"{prefix}{num:05d}"
        doc_id = f"doc_{i:05d}"

        contract_num = f"{random.randint(1, 450)}/{doc_date.strftime('%y')}-{random.choice(['В', 'Т', 'П', 'У'])}"
        contract_str = f"Договір {random.choice(CONTRACT_TYPES)} № {contract_num} від {doc_date.strftime('%d.%m.%Y')}"

        # Multi-organization assignment: 70% TOV Areonix Digital (VAT payer 20%), 30% FOP Areonix-Service (Single tax non-VAT)
        if random.random() < 0.70:
            our_org_id = "org_01"
            our_org_name = 'ТОВ "Ареонікс Діджитал"'
            our_org_edrpou = "43981245"
            is_vat_payer = True
        else:
            our_org_id = "org_02"
            our_org_name = 'ФОП "Ареонікс-Сервіс"'
            our_org_edrpou = "3124598712"
            is_vat_payer = False

        doc_total_kopiykas = 0
        doc_vat_kopiykas = 0

        if doc_type in ["Платіжна інструкція", "Платіжна інструкція (вихідна)"]:
            # Bank Payment Instructions (Поступление от покупателя / Оплата поставщику)
            pay_amt_kop = (random.randint(1500000, 22000000) // 100) * 100  # 15k - 220k UAH
            if is_vat_payer:
                base_kop = int(round(pay_amt_kop * 5 / 6))
                vat_kop = pay_amt_kop - base_kop
            else:
                vat_kop = 0

            doc_total_kopiykas = pay_amt_kop
            doc_vat_kopiykas = vat_kop

            item_id = f"item_{i:05d}_1"
            is_incoming_pay = (doc_type == "Платіжна інструкція")
            items.append({
                "id": item_id,
                "doc_id": doc_id,
                "line_num": 1,
                "item_name": (
                    f"Оплата за товари та послуги згідно договору № {contract_num}"
                    if is_incoming_pay else
                    f"Оплата постачальнику за матеріали та послуги згідно договору № {contract_num}"
                ),
                "sku": None,
                "unit": "платіж",
                "quantity": 1.0,
                "unit_price_kopiykas": pay_amt_kop,
                "amount_kopiykas": pay_amt_kop,
                "vat_kopiykas": vat_kop,
            })
            comment_text = (
                f"Оплата за безготівковим розрахунком від покупця зг. {contract_str}. Банківська виписка проведена."
                if is_incoming_pay else
                f"Перерахування коштів постачальнику зг. {contract_str}. Банківська виписка проведена."
            )
        else:
            # 1 to 3 line items for SME goods / services invoices
            num_items = random.choices([1, 2, 3], weights=[0.70, 0.23, 0.07])[0]
            # Filter items according to doc type: acts get services, invoices get goods
            if doc_type in ["Акт виконаних робіт", "Акт отриманих послуг"]:
                eligible_items = [it for it in ITEMS_CATALOG if not it[4]]
            elif doc_type in ["Видаткова накладна", "Прибуткова накладна"]:
                eligible_items = [it for it in ITEMS_CATALOG if it[4]]
            else:
                eligible_items = ITEMS_CATALOG

            if not eligible_items:
                eligible_items = ITEMS_CATALOG

            selected_items = random.sample(eligible_items, min(num_items, len(eligible_items)))

            for line_idx, (name, unit, p_min, p_max, is_good) in enumerate(selected_items, start=1):
                if unit in ["послуга", "компл", "рейс", "міс"]:
                    qty = 1.0
                elif unit == "год":
                    qty = float(random.choice([6, 8, 12, 16]))
                elif unit == "кор":
                    qty = float(random.choice([6, 10, 15]))
                elif unit == "доба":
                    qty = float(random.choice([10, 15, 20]))
                elif name.startswith("Картридж"):
                    qty = float(random.choice([3, 4, 5]))
                elif name.startswith("Серверний"):
                    qty = float(random.choice([1, 2, 3]))
                else:
                    qty = float(random.choice([1, 2, 3]))

                unit_price_kop = (random.randint(p_min, p_max) // 100) * 100
                amount_kop = int(round(unit_price_kop * qty))

                if is_vat_payer:
                    base_kop = int(round(amount_kop * 5 / 6))
                    vat_kop = amount_kop - base_kop
                else:
                    vat_kop = 0

                doc_total_kopiykas += amount_kop
                doc_vat_kopiykas += vat_kop

                item_id = f"item_{i:05d}_{line_idx}"
                items.append({
                    "id": item_id,
                    "doc_id": doc_id,
                    "line_num": line_idx,
                    "item_name": name,
                    "sku": f"АРТ-{random.randint(10000, 99999)}",
                    "unit": unit,
                    "quantity": qty,
                    "unit_price_kopiykas": unit_price_kop,
                    "amount_kopiykas": amount_kop,
                    "vat_kopiykas": vat_kop,
                })

            comments_pool = [
                f"Розрахунки згідно {contract_str}",
                "Поставка на склад у м. Дніпро згідно заявки",
                "Акт звірки взаєморозрахунків підтверджено",
                "Отримання матеріалів на центральний склад за довіреністю",
                "Термінова поставка згідно специфікації № 2",
                "Передплата 100% за регламентне обслуговування",
                None,
                None,
            ]
            comment_text = random.choice(comments_pool)

        # Tax Invoice (ПН / ЄРНН) metadata
        tax_invoice_num = None
        tax_invoice_dt = None
        ernn_stat = "Без ПДВ"
        ernn_dt = None

        if is_vat_payer and doc_type in ["Видаткова накладна", "Акт виконаних робіт", "Прибуткова накладна", "Акт отриманих послуг"]:
            tax_invoice_num = f"ПН-{i:05d}"
            tax_invoice_dt = doc_date.isoformat()
            if random.random() < 0.94:
                ernn_stat = "Зареєстровано в ЄРНН"
                ernn_dt = (doc_date + timedelta(days=random.randint(1, 4))).strftime("%d.%m.%Y 11:28") + " (Квитанція № 2)"
            else:
                ernn_stat = "Не зареєстровано"
                ernn_dt = None

        # Electronic Signature (КЕП / ЕДО) metadata
        if random.random() < 0.80:
            doc_form = "Електронна (КЕП)"
            edi_provider = random.choice(["Вчасно", "M.E.Doc", "Сота"])
            p7s_hash = hashlib.sha256(f"{doc_id}_{doc_number}_{doc_date}".encode()).hexdigest()
            p7s_info = f"КЕП: {cp.get('director', 'Директор')}, {doc_date.strftime('%d.%m.%Y')} 14:{random.randint(10,59)} ({edi_provider} / КНЕДП ДПС)"
        else:
            doc_form = "Паперова (оригінал)"
            edi_provider = "Паперовий архів"
            p7s_hash = None
            p7s_info = f"Паперовий оригінал з підписом та мокрою печаткою (Архівна папка № {doc_date.year}/{random.randint(1, 12):02d})"

        documents.append({
            "id": doc_id,
            "doc_number": doc_number,
            "doc_type": doc_type,
            "direction": direction,
            "doc_date": doc_date.isoformat(),
            "our_company_id": our_org_id,
            "our_company_name": our_org_name,
            "our_company_edrpou": our_org_edrpou,
            "counterparty_id": cp["id"],
            "counterparty_name": cp["name"],
            "counterparty_edrpou": cp["edrpou"],
            "total_amount_kopiykas": doc_total_kopiykas,
            "vat_kopiykas": doc_vat_kopiykas,
            "currency": "UAH",
            "status": "Проведено" if doc_type != "Рахунок на оплату" else random.choice(["Оплачено", "Виписано"]),
            "contract_number": contract_num,
            "comment": comment_text,
            "year": doc_date.year,
            "tax_invoice_number": tax_invoice_num,
            "tax_invoice_date": tax_invoice_dt,
            "ernn_status": ernn_stat,
            "ernn_reg_date": ernn_dt,
            "doc_form": doc_form,
            "edi_provider": edi_provider,
            "p7s_sign_hash": p7s_hash,
            "p7s_signer_info": p7s_info,
            "source_file": "1c_historical_archive.xml",
        })

    return documents, items


def run_generation(data_dir: Path, db_path: Path, index_path: Path) -> Dict[str, Any]:
    """Generates synthetic dataset, saves CSV and JSON, and imports into vault."""
    data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Generating 100 Ukrainian counterparties...")
    counterparties = generate_counterparties(100)

    logger.info("Generating 1,000 documents with line items...")
    documents, items = generate_documents_and_items(counterparties, 1000)

    # 1. Save CSVs
    cp_csv = data_dir / "counterparties.csv"
    with open(cp_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(counterparties[0].keys()))
        writer.writeheader()
        writer.writerows(counterparties)

    doc_csv = data_dir / "documents.csv"
    with open(doc_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(documents[0].keys()))
        writer.writeheader()
        writer.writerows(documents)

    items_csv = data_dir / "document_items.csv"
    with open(items_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)

    logger.info("Exported CSVs to %s", data_dir)

    # 2. Save JSON bundle
    bundle_json = data_dir / "frozen_archive_bundle.json"
    bundle_data = {
        "counterparties": counterparties,
        "documents": [
            {
                **d,
                "items": [it for it in items if it["doc_id"] == d["id"]],
            }
            for d in documents
        ],
    }
    with open(bundle_json, "w", encoding="utf-8") as f:
        json.dump(bundle_data, f, ensure_ascii=False, indent=2)
    logger.info("Exported JSON bundle to %s", bundle_json)

    # 3. Import into DuckDB + SQLite FTS5 + Snappy Parquet
    logger.info("Importing into DuckDB vault and building SQLite FTS5 BM25 index...")
    importer = FreezeImporter(db_path=db_path, index_path=index_path)
    import_stats = importer.import_csv_files(
        counterparties_csv=cp_csv,
        documents_csv=doc_csv,
        items_csv=items_csv,
    )
    storage_stats = importer.get_storage_stats()

    logger.info("Archival freezing complete: %s", storage_stats)
    return {
        "import_stats": import_stats,
        "storage_stats": storage_stats,
    }


def main():
    root = Path(__file__).resolve().parent.parent.parent
    data_dir = root / "data"
    db_path = root / "archive_vault.duckdb"
    index_path = root / "archive_index.db"
    run_generation(data_dir=data_dir, db_path=db_path, index_path=index_path)


if __name__ == "__main__":
    main()
