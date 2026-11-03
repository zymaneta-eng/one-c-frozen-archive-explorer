#!/usr/bin/env python3
"""
1C Frozen Archive Explorer - Direct SQL Data Extractor
Export counterparties, documents, and line items directly from 1C Enterprise / BAS
databases running on Microsoft SQL Server or PostgreSQL into standardized CSV files.

Outputs:
  - counterparties.csv
  - documents.csv
  - document_items.csv

Usage:
  python tools/export_from_sql.py --db-type mssql --host 192.168.1.50 --database enterprise_1c --user sa --password secret --out-dir ./data
  python tools/export_from_sql.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("export_from_sql")


# ---------------------------------------------------------------------------
# DEFAULT 1C DATABASE QUERIES & SCHEMAS
# ---------------------------------------------------------------------------

DEFAULT_QUERIES = {
    "counterparties": """
        SELECT
            c._IDRRef AS id,
            COALESCE(c._Fld1234, '') AS edrpou,
            COALESCE(c._Description, '') AS name,
            COALESCE(c._Fld1235, c._Description) AS short_name,
            CASE WHEN LEN(c._Fld1234) = 10 THEN 1 ELSE 0 END AS is_fop,
            COALESCE(c._Fld1236, 'Загальна система') AS tax_system,
            COALESCE(ba._Fld2345, '') AS iban,
            COALESCE(b._Description, '') AS bank_name,
            COALESCE(c._Fld1237, '') AS address,
            COALESCE(c._Fld1238, '') AS phone,
            COALESCE(c._Fld1239, '') AS email,
            COALESCE(c._Fld1240, '') AS director
        FROM _Reference112 c
        LEFT JOIN _Reference115 ba ON c._Fld1241RRef = ba._IDRRef
        LEFT JOIN _Reference118 b ON ba._Fld2346RRef = b._IDRRef
        WHERE c._Marked = 0
    """,
    "documents": """
        SELECT
            d._IDRRef AS id,
            d._Number AS doc_number,
            'Видаткова накладна' AS doc_type,
            CAST(d._Date_Time AS DATE) AS doc_date,
            o._IDRRef AS our_company_id,
            o._Description AS our_company_name,
            COALESCE(o._Fld1234, '') AS our_company_edrpou,
            c._IDRRef AS counterparty_id,
            c._Description AS counterparty_name,
            COALESCE(c._Fld1234, '') AS counterparty_edrpou,
            d._Fld3456 AS total_amount,
            d._Fld3457 AS vat_amount,
            'UAH' AS currency,
            CASE WHEN d._Posted = 1 THEN 'Проведено' ELSE 'Не проведено' END AS status,
            COALESCE(agr._Number, '') AS contract_number,
            COALESCE(d._Fld3458, '') AS comment,
            YEAR(d._Date_Time) AS year
        FROM _Document220 d
        LEFT JOIN _Reference112 c ON d._Fld3459RRef = c._IDRRef
        LEFT JOIN _Reference110 o ON d._Fld3460RRef = o._IDRRef
        LEFT JOIN _Reference113 agr ON d._Fld3461RRef = agr._IDRRef
        WHERE d._Marked = 0
    """,
    "document_items": """
        SELECT
            t._KeyField AS id,
            t._Document220_IDRRef AS doc_id,
            t._LineNo AS line_num,
            nom._Description AS item_name,
            COALESCE(nom._Code, '') AS sku,
            COALESCE(u._Description, 'шт') AS unit,
            t._Fld4567 AS quantity,
            t._Fld4568 AS unit_price,
            t._Fld4569 AS amount,
            t._Fld4570 AS vat_amount
        FROM _Document220_VT4565 t
        LEFT JOIN _Reference125 nom ON t._Fld4566RRef = nom._IDRRef
        LEFT JOIN _Reference128 u ON nom._Fld5678RRef = u._IDRRef
    """,
}


def build_connection_string(args: argparse.Namespace) -> str:
    """Constructs database connection string based on db-type and parameters."""
    if args.db_type == "mssql":
        driver = args.driver or "ODBC Driver 18 for SQL Server"
        trust_cert = "yes" if args.trust_server_certificate else "no"
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={args.host},{args.port};"
            f"DATABASE={args.database};"
            f"UID={args.user};"
            f"PWD={args.password};"
            f"TrustServerCertificate={trust_cert};"
        )
    elif args.db_type == "postgres":
        return (
            f"postgresql://{args.user}:{args.password}@"
            f"{args.host}:{args.port}/{args.database}"
        )
    elif args.db_type == "sqlite":
        return args.database
    else:
        raise ValueError(f"Unsupported database type: {args.db_type}")


def export_query_to_csv(
    cursor: Any,
    query: str,
    out_file: Path,
    limit: Optional[int] = None,
) -> int:
    """Executes query and writes resulting rows directly to UTF-8 BOM CSV."""
    if limit and limit > 0:
        query = f"{query.strip()} LIMIT {limit}" if "LIMIT" not in query.upper() else query

    logger.info("Executing extraction query for %s...", out_file.name)
    cursor.execute(query)

    columns = [col[0] for col in cursor.description]
    out_file.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)

        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for r in rows:
                formatted_row = []
                for val in r:
                    if isinstance(val, (date, datetime)):
                        formatted_row.append(val.strftime("%Y-%m-%d"))
                    elif isinstance(val, bytes):
                        # Convert binary UUID / 1C GUID to hex string
                        formatted_row.append(val.hex())
                    elif val is None:
                        formatted_row.append("")
                    else:
                        formatted_row.append(str(val))
                writer.writerow(formatted_row)
                count += 1

    logger.info("Successfully exported %d rows to %s", count, out_file)
    return count


def run_dry_run(out_dir: Path) -> None:
    """Generates verification sample files to test downstream freeze importer pipeline."""
    logger.info("[DRY-RUN] Simulating SQL extraction into %s...", out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sample counterparties
    cp_path = out_dir / "counterparties.csv"
    with open(cp_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "edrpou", "name", "short_name", "is_fop", "tax_system", "iban", "bank_name", "address", "phone", "email", "director"])
        writer.writerow(["cp_0001", "43981245", 'ТОВ "Ареонікс Діджитал"', 'ТОВ "Ареонікс Діджитал"', "0", "Платник ПДВ на загальних підставах", "UA213052990000026001234567890", 'АТ КБ "ПриватБанк"', "м. Київ, вул. Хрещатик, 22", "+380441234567", "info@areonix.ua", "Коваленко О. В."])
        writer.writerow(["cp_0002", "3124598712", 'ФОП Козак Олександр Сергійович', 'ФОП Козак О. С.', "1", "Спрощена система (єдиний податок, 3 група)", "UA843004650000026009876543210", 'АТ "Ощадбанк"', "м. Львів, вул. Шевченка, 111", "+380671234567", "kozak@gmail.com", "Козак О. С."])

    # 2. Sample documents (Shipment + Payment)
    doc_path = out_dir / "documents.csv"
    with open(doc_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "doc_number", "doc_type", "doc_date", "our_company_id", "our_company_name", "our_company_edrpou", "counterparty_id", "counterparty_name", "counterparty_edrpou", "total_amount", "vat_amount", "currency", "status", "contract_number", "comment", "year"])
        writer.writerow(["doc_001", "РН-00001", "Видаткова накладна", "2024-05-10", "org_01", 'ТОВ "Ареонікс Діджитал"', "43981245", "cp_0002", "ФОП Козак Олександр Сергійович", "3124598712", "42446.00", "7074.33", "UAH", "Проведено", "Договір поставки № 12", "Поставка товару згідно специфікації", "2024"])
        writer.writerow(["doc_002", "ПІ-00001", "Платіжна інструкція", "2024-05-15", "org_01", 'ТОВ "Ареонікс Діджитал"', "43981245", "cp_0002", "ФОП Козак Олександр Сергійович", "3124598712", "42446.00", "7074.33", "UAH", "Проведено", "Договір поставки № 12", "Повна оплата за РН-00001", "2024"])

    # 3. Sample line items
    item_path = out_dir / "document_items.csv"
    with open(item_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "doc_id", "line_num", "item_name", "sku", "unit", "quantity", "unit_price", "amount", "vat_amount"])
        writer.writerow(["item_001", "doc_001", "1", "Маршрутизатор MikroTik CCR2004", "АРТ-10294", "шт", "2", "21223.00", "42446.00", "7074.33"])
        writer.writerow(["item_002", "doc_002", "1", "Оплата за мережеве обладнання по РН-00001", "", "платіж", "1", "42446.00", "42446.00", "7074.33"])

    logger.info("[DRY-RUN] Verification CSVs generated in %s", out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="1C Frozen Archive Explorer - Direct Database SQL Extractor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db-type", choices=["mssql", "postgres", "sqlite"], default="mssql", help="Database type")
    parser.add_argument("--host", default="localhost", help="Database server hostname or IP")
    parser.add_argument("--port", type=int, default=1433, help="Database server port (1433 for MSSQL, 5432 for Postgres)")
    parser.add_argument("--database", default="ib_enterprise", help="Database name")
    parser.add_argument("--user", default="sa", help="Database user")
    parser.add_argument("--password", default="", help="Database password")
    parser.add_argument("--driver", default="ODBC Driver 18 for SQL Server", help="ODBC Driver for MSSQL")
    parser.add_argument("--trust-server-certificate", action="store_true", help="Trust server SSL certificate (MSSQL)")
    parser.add_argument("--out-dir", type=Path, default=Path("./data"), help="Target output directory for CSV files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to extract (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode without connecting to SQL")

    args = parser.parse_args()

    if args.dry_run:
        run_dry_run(args.out_dir)
        return

    logger.info("Initializing direct extraction from %s (%s:%d)...", args.db_type.upper(), args.host, args.port)

    # Establish connection
    try:
        if args.db_type == "mssql":
            try:
                import pyodbc
            except ImportError:
                logger.error("pyodbc is required for MS SQL extraction. Install: pip install pyodbc")
                sys.exit(1)
            conn_str = build_connection_string(args)
            conn = pyodbc.connect(conn_str)
        elif args.db_type == "postgres":
            try:
                import psycopg2
            except ImportError:
                logger.error("psycopg2 is required for PostgreSQL extraction. Install: pip install psycopg2-binary")
                sys.exit(1)
            conn = psycopg2.connect(
                host=args.host,
                port=args.port,
                dbname=args.database,
                user=args.user,
                password=args.password,
            )
        elif args.db_type == "sqlite":
            import sqlite3
            conn = sqlite3.connect(args.database)
        else:
            raise ValueError(f"Unknown db-type: {args.db_type}")

        cursor = conn.cursor()
        logger.info("Connected to 1C database successfully.")

        # Export counterparties
        cp_file = args.out_dir / "counterparties.csv"
        export_query_to_csv(cursor, DEFAULT_QUERIES["counterparties"], cp_file)

        # Export documents
        doc_file = args.out_dir / "documents.csv"
        export_query_to_csv(cursor, DEFAULT_QUERIES["documents"], doc_file, limit=args.limit)

        # Export line items
        item_file = args.out_dir / "document_items.csv"
        export_query_to_csv(cursor, DEFAULT_QUERIES["document_items"], item_file)

        cursor.close()
        conn.close()
        logger.info("Export completed successfully. CSV files ready in %s", args.out_dir)

    except Exception as e:
        logger.error("Database extraction failed: %s", e)
        logger.info("Tip: You can use --dry-run to generate sample files, or review tools/1c_export_snippet.bsl for direct in-1C export.")
        sys.exit(1)


if __name__ == "__main__":
    main()
