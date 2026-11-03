"""
1C Frozen Archive Explorer - FastAPI Web Server
Air-gapped, zero-license, zero-cloud-token web server with sub-50ms search,
Excel (.xlsx) exports via openpyxl, and printable accounting documents.
"""

from __future__ import annotations

import io
import math
import os
import urllib.parse
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from one_c_frozen_archive_explorer.schema import (
    ArchiveStatsModel,
    DocumentDetailModel,
    format_kopiykas,
    kopiykas_to_uah_float,
)
from one_c_frozen_archive_explorer.search_engine import SearchEngine


def get_default_paths() -> tuple[Path, Path]:
    """Resolves database file paths reliably across environments."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    db_env = os.getenv("VAULT_DB_PATH")
    index_env = os.getenv("INDEX_DB_PATH")

    db_path = Path(db_env) if db_env else (base_dir / "archive_vault.duckdb")
    index_path = Path(index_env) if index_env else (base_dir / "archive_index.db")

    # If running from another working dir and files are in cwd, use cwd
    cwd_db = Path.cwd() / "archive_vault.duckdb"
    cwd_idx = Path.cwd() / "archive_index.db"
    if not db_path.exists() and cwd_db.exists():
        db_path = cwd_db
    if not index_path.exists() and cwd_idx.exists():
        index_path = cwd_idx

    return db_path, index_path


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application."""
    app = FastAPI(
        title="1C Frozen Archive Explorer",
        description="Air-gapped, zero-license Ukrainian 1C/BAS historical accounting archive",
        version="1.0.0",
        docs_url=None,  # Air-gapped - disable external Swagger CDN calls
        redoc_url=None,
    )

    module_dir = Path(__file__).resolve().parent
    templates_dir = module_dir / "templates"
    static_dir = module_dir / "static"

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))

    # Add custom Jinja filters
    def format_date_ua(date_str: str | None) -> str:
        """Converts YYYY-MM-DD -> DD.MM.YYYY for Ukrainian accounting standards."""
        if not date_str:
            return ""
        parts = str(date_str).strip().split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return str(date_str)

    def format_money_html(amount_kopiykas: int | None, currency: str = "₴") -> str:
        """
        Formats kopiykas into financial HTML with non-breaking tabular numbers and muted currency symbol.
        e.g. 4244600 -> '42 446,00&nbsp;<span class="amount-curr">₴</span>'
        """
        if amount_kopiykas is None:
            amount_kopiykas = 0
        is_negative = amount_kopiykas < 0
        abs_kop = abs(amount_kopiykas)
        hryvnias = abs_kop // 100
        kop = abs_kop % 100
        hryvnias_str = f"{hryvnias:,}".replace(",", " ")
        sign = "-" if is_negative else ""
        return f'{sign}{hryvnias_str},{kop:02d}&nbsp;<span class="amount-curr" style="color: #94a3b8; font-weight: 400; font-size: 0.9em;">{currency}</span>'

    templates.env.filters["format_kopiykas"] = format_kopiykas
    templates.env.filters["format_date_ua"] = format_date_ua
    templates.env.filters["format_money_html"] = format_money_html

    db_path, index_path = get_default_paths()
    engine = SearchEngine(db_path=db_path, index_path=index_path)

    # -----------------------------------------------------------------------
    # HTML PAGES
    # -----------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index_page(
        request: Request,
        q: str = Query(default="", description="Search query"),
        doc_type: Optional[str] = Query(default=None),
        year: Optional[str] = Query(default=None),
        our_company_id: Optional[str] = Query(default=None),
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=25, ge=1, le=100),
    ):
        """Main archive search explorer interface with multi-org filtering."""
        parsed_year = int(year) if year and year.isdigit() else None
        offset = (page - 1) * limit

        results, total_count, exec_ms = engine.search(
            query=q,
            doc_type=doc_type,
            year=parsed_year,
            our_company_id=our_company_id,
            limit=limit,
            offset=offset,
        )

        stats = engine.get_archive_stats(our_company_id=our_company_id)
        worm_manifest = engine.get_worm_manifest()
        total_pages = max(1, math.ceil(total_count / limit))
        detected_cp = engine.detect_counterparty(query=q, current_results=results)

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "stats": stats,
                "results": results,
                "total_count": total_count,
                "execution_ms": exec_ms,
                "query": q,
                "current_type": doc_type or "",
                "current_year": parsed_year,
                "selected_org": our_company_id or "",
                "worm_manifest": worm_manifest,
                "current_page": page,
                "total_pages": total_pages,
                "detected_counterparty": detected_cp,
            },
        )

    @app.get("/document/{doc_id}", response_class=HTMLResponse)
    async def document_detail_page(request: Request, doc_id: str):
        """Dedicated document card view with full line items and counterparty card."""
        doc = engine.get_document_details(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Документ з ID '{doc_id}' не знайдено.")

        return templates.TemplateResponse(
            request=request,
            name="document.html",
            context={
                "doc": doc,
            },
        )

    @app.get("/document/{doc_id}/print", response_class=HTMLResponse)
    async def document_print_view(request: Request, doc_id: str):
        """Official clean printable accounting document view (Ctrl+P ready)."""
        doc = engine.get_document_details(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Документ з ID '{doc_id}' не знайдено.")

        return templates.TemplateResponse(
            request=request,
            name="print_view.html",
            context={
                "doc": doc,
            },
        )

    # -----------------------------------------------------------------------
    # REST API ENDPOINTS (< 50ms responses)
    # -----------------------------------------------------------------------

    @app.get("/api/search")
    async def api_search(
        q: str = Query(default=""),
        doc_type: Optional[str] = Query(default=None),
        year: Optional[int] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        """Sub-50ms hybrid FTS5 + DuckDB search API."""
        results, total_count, exec_ms = engine.search(
            query=q,
            doc_type=doc_type,
            year=year,
            limit=limit,
            offset=offset,
        )
        return {
            "query": q,
            "total_count": total_count,
            "execution_ms": exec_ms,
            "results": [r.model_dump() for r in results],
        }

    @app.get("/api/suggest")
    async def api_suggest(q: str = Query(default="", min_length=1)):
        """Instant autocomplete endpoint."""
        suggestions = engine.suggest(prefix=q, limit=8)
        return suggestions

    @app.get("/api/document/{doc_id}")
    async def api_document(doc_id: str):
        """Returns JSON details of a document including computed financial fields."""
        doc = engine.get_document_details(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не знайдено")
        res = doc.model_dump()
        res["total_in_words"] = doc.total_in_words
        res["formatted_total"] = doc.formatted_total
        res["formatted_vat"] = doc.formatted_vat
        res["formatted_without_vat"] = doc.formatted_without_vat
        res["amount_without_vat_kopiykas"] = doc.amount_without_vat_kopiykas
        return res

    @app.get("/api/stats")
    async def api_stats(our_company_id: Optional[str] = Query(default=None)):
        """Returns archive summary statistics."""
        org_filter = None if not our_company_id or our_company_id in ("all", "") else our_company_id
        return engine.get_archive_stats(our_company_id=org_filter).model_dump()

    # -----------------------------------------------------------------------
    # EXCEL (.xlsx) EXPORT ENDPOINTS
    # -----------------------------------------------------------------------

    @app.get("/export/document/{doc_id}/excel")
    async def export_document_excel(doc_id: str):
        """Exports a single document to formatted Excel (.xlsx) using openpyxl."""
        doc = engine.get_document_details(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Документ не знайдено")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{doc.doc_number}"[:31]

        # Styling definitions
        font_header = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
        font_sub = Font(name="Calibri", size=11, bold=True)
        font_regular = Font(name="Calibri", size=10)
        font_bold = Font(name="Calibri", size=10, bold=True)
        font_italic = Font(name="Calibri", size=9, italic=True)

        fill_header = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_tbl_head = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        fill_total = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")

        # Title Row
        ws.merge_cells("A1:G1")
        cell_title = ws["A1"]
        cell_title.value = f"{doc.doc_type.upper()} № {doc.doc_number} від {doc.doc_date} р."
        cell_title.font = font_header
        cell_title.fill = fill_header
        cell_title.alignment = align_center
        ws.row_dimensions[1].height = 32

        # Credentials
        ws["A3"] = "Постачальник:"
        ws["A3"].font = font_sub
        ws["B3"] = "ТОВ \"АРХІВНЕ ПІДПРИЄМСТВО\" (ЄДРПОУ: 38291045, IBAN: UA213052990000026001234567890)"
        ws["B3"].font = font_regular

        ws["A4"] = "Одержувач:"
        ws["A4"].font = font_sub
        ws["B4"] = f"{doc.counterparty_name} (ЄДРПОУ/ІПН: {doc.counterparty_edrpou})"
        ws["B4"].font = font_regular

        ws["A5"] = "Підстава / Договір:"
        ws["A5"].font = font_sub
        ws["B5"] = doc.contract_number or "Без договору"
        ws["B5"].font = font_regular

        if doc.comment:
            ws["A6"] = "Примітка:"
            ws["A6"].font = font_sub
            ws["B6"] = doc.comment
            ws["B6"].font = font_italic

        # Items Table Header
        start_row = 8
        headers = ["№", "Найменування товару або послуги", "Артикул", "Од.", "Кількість", "Ціна без ПДВ (грн)", "Сума без ПДВ (грн)"]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=start_row, column=col_idx, value=h)
            cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
            cell.fill = fill_tbl_head
            cell.alignment = align_center
            cell.border = thin_border
        ws.row_dimensions[start_row].height = 24

        # Items Rows
        curr_row = start_row + 1
        for it in doc.items:
            unit_price_uah = kopiykas_to_uah_float(it.unit_price_kopiykas)
            amount_uah = kopiykas_to_uah_float(it.amount_kopiykas)

            r_data = [
                (it.line_num, align_center, None),
                (it.item_name, align_left, None),
                (it.sku or "—", align_center, None),
                (it.unit, align_center, None),
                (it.quantity, align_right, "#,##0.00"),
                (unit_price_uah, align_right, "#,##0.00"),
                (amount_uah, align_right, "#,##0.00"),
            ]

            for col_idx, (val, al, num_fmt) in enumerate(r_data, start=1):
                c = ws.cell(row=curr_row, column=col_idx, value=val)
                c.font = font_regular
                c.alignment = al
                c.border = thin_border
                if num_fmt:
                    c.number_format = num_fmt

            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        # Totals Section
        vat_uah = kopiykas_to_uah_float(doc.vat_kopiykas)
        total_uah = kopiykas_to_uah_float(doc.total_amount_kopiykas)
        without_vat_uah = kopiykas_to_uah_float(doc.amount_without_vat_kopiykas)

        totals_entries = [
            ("Разом без ПДВ:", without_vat_uah),
            ("ПДВ 20%:", vat_uah),
            ("Всього з ПДВ:", total_uah),
        ]

        for label, val in totals_entries:
            ws.cell(row=curr_row, column=6, value=label).font = font_bold
            ws.cell(row=curr_row, column=6).alignment = align_right

            c_total = ws.cell(row=curr_row, column=7, value=val)
            c_total.font = font_bold
            c_total.alignment = align_right
            c_total.number_format = "#,##0.00\\ ₴"
            c_total.fill = fill_total
            c_total.border = thin_border
            curr_row += 1

        # Words description
        curr_row += 1
        ws.cell(row=curr_row, column=1, value="Сума прописом:").font = font_bold
        ws.cell(row=curr_row, column=2, value=doc.total_in_words).font = font_italic

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len and "\n" not in val and cell.row > 2:
                    max_len = len(val)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 10)

        # Explicitly wider for description column
        ws.column_dimensions["B"].width = 46

        # Write to stream
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        safe_filename = f"{doc.doc_number}_{doc.doc_date}.xlsx"
        encoded_filename = urllib.parse.quote(safe_filename)

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
        )

    # -----------------------------------------------------------------------
    # RECONCILIATION ACT & WORM MANIFEST
    # -----------------------------------------------------------------------

    @app.get("/reconciliation/{counterparty_id}", response_class=HTMLResponse)
    async def reconciliation_page(
        request: Request,
        counterparty_id: str,
        our_company_id: Optional[str] = Query(default=None),
        start_date: Optional[str] = Query(default=None),
        end_date: Optional[str] = Query(default=None),
    ):
        """Official Ukrainian mutual reconciliation act (Акт звірки взаєморозрахунків)."""
        report = engine.get_reconciliation(
            counterparty_id=counterparty_id,
            our_company_id=our_company_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not report:
            raise HTTPException(status_code=404, detail=f"Контрагента '{counterparty_id}' не знайдено.")

        stats = engine.get_archive_stats()

        return templates.TemplateResponse(
            request=request,
            name="reconciliation_act.html",
            context={
                "report": report,
                "selected_org": our_company_id or report.our_company_id,
                "our_companies": stats.our_companies,
            },
        )

    @app.get("/api/reconciliation/{counterparty_id}")
    async def reconciliation_api(
        counterparty_id: str,
        our_company_id: Optional[str] = Query(default=None),
        start_date: Optional[str] = Query(default=None),
        end_date: Optional[str] = Query(default=None),
    ):
        """JSON endpoint returning structured ledger calculation for reconciliation."""
        report = engine.get_reconciliation(
            counterparty_id=counterparty_id,
            our_company_id=our_company_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not report:
            raise HTTPException(status_code=404, detail="Counterparty not found")
        return report.model_dump()

    @app.get("/reports/dps-registry", response_class=HTMLResponse)
    async def dps_registry_report(
        request: Request,
        q: str = Query(default=""),
        doc_type: Optional[str] = Query(default=None),
        year: Optional[str] = Query(default=None),
        our_company_id: Optional[str] = Query(default=None),
        start_date: Optional[str] = Query(default=None),
        end_date: Optional[str] = Query(default=None),
    ):
        """Official summary registry of primary accounting documents for State Tax Service (ДПС)."""
        parsed_year = int(year) if year and year.isdigit() else None
        registry = engine.get_dps_registry(
            query=q,
            doc_type=doc_type,
            year=parsed_year,
            our_company_id=our_company_id,
            start_date=start_date,
            end_date=end_date,
        )

        return templates.TemplateResponse(
            request=request,
            name="dps_registry.html",
            context={
                "registry": registry,
            },
        )

    @app.get("/export/reconciliation/{counterparty_id}/excel")
    async def export_reconciliation_excel(
        counterparty_id: str,
        our_company_id: Optional[str] = Query(default=None),
        start_date: Optional[str] = Query(default=None),
        end_date: Optional[str] = Query(default=None),
    ):
        """Exports bilateral reconciliation act to professional Excel (.xlsx) spreadsheet."""
        report = engine.get_reconciliation(
            counterparty_id=counterparty_id,
            our_company_id=our_company_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not report:
            raise HTTPException(status_code=404, detail="Контрагента не знайдено")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Акт звірки"

        font_title = Font(name="Calibri", size=13, bold=True)
        font_sub = Font(name="Calibri", size=10, italic=True)
        font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        font_bold = Font(name="Calibri", size=10, bold=True)
        font_regular = Font(name="Calibri", size=10)

        fill_our = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        fill_cp = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        fill_subhead = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        fill_totals = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        double_bottom = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="double", color="000000"),
        )

        ws.merge_cells("A1:G1")
        ws["A1"] = "АКТ ЗВІРКИ ВЗАЄМНИХ РОЗРАХУНКІВ"
        ws["A1"].font = font_title
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 24

        ws.merge_cells("A2:G2")
        ws["A2"] = f"за період: з {format_date_ua(report.start_date)} по {format_date_ua(report.end_date)}"
        ws["A2"].font = font_sub
        ws["A2"].alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("A3:G3")
        ws["A3"] = f"між {report.our_company_name} (ЄДРПОУ: {report.our_company_edrpou}) та {report.counterparty.name} (ЄДРПОУ/ІПН: {report.counterparty.edrpou})"
        ws["A3"].font = Font(name="Calibri", size=9.5)
        ws["A3"].alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("A5:D5")
        ws["A5"] = f"За даними: {report.our_company_name}"
        ws["A5"].font = font_header
        ws["A5"].fill = fill_our
        ws["A5"].alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("E5:G5")
        ws["E5"] = f"За даними: {report.counterparty.name}"
        ws["E5"].font = font_header
        ws["E5"].fill = fill_cp
        ws["E5"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[5].height = 22

        headers_6 = [
            (1, "Дата"), (2, "Документ / Операція"), (3, "Дебет (грн)"), (4, "Кредит (грн)"),
            (5, "Документ / Оплата"), (6, "Дебет (грн)"), (7, "Кредит (грн)")
        ]
        for col_idx, text in headers_6:
            c = ws.cell(row=6, column=col_idx, value=text)
            c.font = font_header
            c.fill = fill_subhead
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = thin_border
        ws.row_dimensions[6].height = 20

        curr_row = 7
        ws.cell(row=curr_row, column=1, value=format_date_ua(report.start_date)).alignment = Alignment(horizontal="center")
        ws.cell(row=curr_row, column=2, value=f"Сальдо початкове на {format_date_ua(report.start_date)}").font = font_bold
        ws.cell(row=curr_row, column=5, value=f"Сальдо початкове на {format_date_ua(report.start_date)}").font = font_bold

        open_kop = report.opening_balance_kopiykas
        open_uah = abs(open_kop) / 100.0

        if open_kop > 0:
            ws.cell(row=curr_row, column=3, value=open_uah)
            ws.cell(row=curr_row, column=4, value=0.0)
            ws.cell(row=curr_row, column=6, value=0.0)
            ws.cell(row=curr_row, column=7, value=open_uah)
        elif open_kop < 0:
            ws.cell(row=curr_row, column=3, value=0.0)
            ws.cell(row=curr_row, column=4, value=open_uah)
            ws.cell(row=curr_row, column=6, value=open_uah)
            ws.cell(row=curr_row, column=7, value=0.0)
        else:
            ws.cell(row=curr_row, column=3, value=0.0)
            ws.cell(row=curr_row, column=4, value=0.0)
            ws.cell(row=curr_row, column=6, value=0.0)
            ws.cell(row=curr_row, column=7, value=0.0)

        for col_idx in (3, 4, 6, 7):
            ws.cell(row=curr_row, column=col_idx).number_format = "#,##0.00"
            ws.cell(row=curr_row, column=col_idx).font = font_bold
        for c in range(1, 8):
            ws.cell(row=curr_row, column=c).border = thin_border
            ws.cell(row=curr_row, column=c).fill = fill_totals

        for entry in report.entries:
            curr_row += 1
            ws.cell(row=curr_row, column=1, value=format_date_ua(entry.date)).alignment = Alignment(horizontal="center")
            ws.cell(row=curr_row, column=2, value=f"{entry.doc_type} № {entry.doc_number}")

            d_val = (entry.debit_kopiykas / 100.0) if entry.debit_kopiykas else None
            c_val = (entry.credit_kopiykas / 100.0) if entry.credit_kopiykas else None

            if d_val is not None:
                cell_d = ws.cell(row=curr_row, column=3, value=d_val)
                cell_d.number_format = "#,##0.00"
            if c_val is not None:
                cell_c = ws.cell(row=curr_row, column=4, value=c_val)
                cell_c.number_format = "#,##0.00"

            ws.cell(row=curr_row, column=5, value=f"{entry.doc_type} № {entry.doc_number}")
            if c_val is not None:
                cell_cp_d = ws.cell(row=curr_row, column=6, value=c_val)
                cell_cp_d.number_format = "#,##0.00"
            if d_val is not None:
                cell_cp_c = ws.cell(row=curr_row, column=7, value=d_val)
                cell_cp_c.number_format = "#,##0.00"

            for c in range(1, 8):
                ws.cell(row=curr_row, column=c).border = thin_border

        curr_row += 1
        ws.cell(row=curr_row, column=2, value="Обороти за період:").font = font_bold
        ws.cell(row=curr_row, column=3, value=(report.total_debit_kopiykas / 100.0)).number_format = "#,##0.00"
        ws.cell(row=curr_row, column=4, value=(report.total_credit_kopiykas / 100.0)).number_format = "#,##0.00"
        ws.cell(row=curr_row, column=3).font = font_bold
        ws.cell(row=curr_row, column=4).font = font_bold

        ws.cell(row=curr_row, column=5, value="Обороти за період:").font = font_bold
        ws.cell(row=curr_row, column=6, value=(report.total_credit_kopiykas / 100.0)).number_format = "#,##0.00"
        ws.cell(row=curr_row, column=7, value=(report.total_debit_kopiykas / 100.0)).number_format = "#,##0.00"
        ws.cell(row=curr_row, column=6).font = font_bold
        ws.cell(row=curr_row, column=7).font = font_bold

        for c in range(1, 8):
            ws.cell(row=curr_row, column=c).border = thin_border
            ws.cell(row=curr_row, column=c).fill = fill_totals

        curr_row += 1
        ws.cell(row=curr_row, column=2, value=f"Сальдо кінцеве на {format_date_ua(report.end_date)}:").font = font_bold
        ws.cell(row=curr_row, column=5, value=f"Сальдо кінцеве на {format_date_ua(report.end_date)}:").font = font_bold

        close_kop = report.closing_balance_kopiykas
        close_uah = abs(close_kop) / 100.0

        if close_kop > 0:
            ws.cell(row=curr_row, column=3, value=close_uah)
            ws.cell(row=curr_row, column=4, value=0.0)
            ws.cell(row=curr_row, column=6, value=0.0)
            ws.cell(row=curr_row, column=7, value=close_uah)
        elif close_kop < 0:
            ws.cell(row=curr_row, column=3, value=0.0)
            ws.cell(row=curr_row, column=4, value=close_uah)
            ws.cell(row=curr_row, column=6, value=close_uah)
            ws.cell(row=curr_row, column=7, value=0.0)
        else:
            ws.cell(row=curr_row, column=3, value=0.0)
            ws.cell(row=curr_row, column=4, value=0.0)
            ws.cell(row=curr_row, column=6, value=0.0)
            ws.cell(row=curr_row, column=7, value=0.0)

        for col_idx in (3, 4, 6, 7):
            ws.cell(row=curr_row, column=col_idx).number_format = "#,##0.00"
            ws.cell(row=curr_row, column=col_idx).font = font_bold
        for c in range(1, 8):
            ws.cell(row=curr_row, column=c).border = double_bottom
            ws.cell(row=curr_row, column=c).fill = fill_totals

        curr_row += 2
        ws.merge_cells(start_row=curr_row, start_column=1, end_row=curr_row, end_column=7)
        c_words = ws.cell(row=curr_row, column=1, value=report.closing_balance_in_words)
        c_words.font = font_bold
        c_words.alignment = Alignment(wrap_text=True)

        curr_row += 2
        ws.cell(row=curr_row, column=1, value=f"Від {report.our_company_name}:").font = font_bold
        ws.cell(row=curr_row, column=5, value=f"Від {report.counterparty.name}:").font = font_bold

        curr_row += 1
        ws.cell(row=curr_row, column=1, value=f"Керівник: ___________________ / {report.our_company_name}").font = font_regular
        ws.cell(row=curr_row, column=5, value=f"Керівник: ___________________ / {report.counterparty.director or ''}").font = font_regular

        curr_row += 1
        ws.cell(row=curr_row, column=1, value="Головний бухгалтер: _________").font = font_regular
        ws.cell(row=curr_row, column=5, value="Головний бухгалтер: _________").font = font_regular

        curr_row += 1
        ws.cell(row=curr_row, column=1, value="М.П.                         Дата: ____________").font = font_sub
        ws.cell(row=curr_row, column=5, value="М.П.                         Дата: ____________").font = font_sub

        col_widths = {1: 14, 2: 36, 3: 16, 4: 16, 5: 36, 6: 16, 7: 16}
        for col_idx, width in col_widths.items():
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = width

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = f"akt_zvirky_{report.counterparty.edrpou}_{report.start_date}_{report.end_date}.xlsx"
        encoded_filename = urllib.parse.quote(filename)

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )

    @app.get("/api/worm/manifest")
    async def worm_manifest_api():
        """Returns cryptographic WORM immutability and SHA-256 integrity audit certificate."""
        return engine.get_worm_manifest().model_dump()

    @app.get("/export/search/excel")
    async def export_search_excel(
        q: str = Query(default=""),
        doc_type: Optional[str] = Query(default=None),
        year: Optional[str] = Query(default=None),
        our_company_id: Optional[str] = Query(default=None),
    ):
        """Exports filtered search results table to Excel (.xlsx) using openpyxl."""
        parsed_year = int(year) if year and year.isdigit() else None
        # Export up to 5000 filtered records
        results, total_count, _ = engine.search(
            query=q,
            doc_type=doc_type,
            year=parsed_year,
            our_company_id=our_company_id,
            limit=5000,
            offset=0,
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Результати пошуку"

        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_regular = Font(name="Calibri", size=10)
        font_bold = Font(name="Calibri", size=10, bold=True)
        fill_head = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_total = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        headers = [
            "№", "Наша організація", "Тип документа", "Номер документа", "Дата",
            "Контрагент", "ЄДРПОУ / ІПН", "Сума з ПДВ (грн)", "Коментар",
        ]

        for col_idx, h in enumerate(headers, start=1):
            c = ws.cell(row=1, column=col_idx, value=h)
            c.font = font_header
            c.fill = fill_head
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = thin_border
        ws.row_dimensions[1].height = 26

        curr_row = 2
        total_sum_kop = 0

        for idx, doc in enumerate(results, start=1):
            amount_uah = kopiykas_to_uah_float(doc.total_amount_kopiykas)
            total_sum_kop += doc.total_amount_kopiykas

            row_data = [
                (idx, Alignment(horizontal="center"), None),
                (doc.our_company_name, Alignment(horizontal="left"), None),
                (doc.doc_type, Alignment(horizontal="left"), None),
                (doc.doc_number, Alignment(horizontal="center"), None),
                (doc.doc_date, Alignment(horizontal="center"), None),
                (doc.counterparty_name, Alignment(horizontal="left"), None),
                (doc.counterparty_edrpou, Alignment(horizontal="center"), None),
                (amount_uah, Alignment(horizontal="right"), "#,##0.00"),
                (doc.comment or "", Alignment(horizontal="left"), None),
            ]

            for col_idx, (val, al, num_fmt) in enumerate(row_data, start=1):
                c = ws.cell(row=curr_row, column=col_idx, value=val)
                c.font = font_regular
                c.alignment = al
                c.border = thin_border
                if num_fmt:
                    c.number_format = num_fmt

            ws.row_dimensions[curr_row].height = 20
            curr_row += 1

        # Summary Total Row
        ws.cell(row=curr_row, column=6, value="РАЗОМ ЗА ВИБІРКОЮ:").font = font_bold
        ws.cell(row=curr_row, column=6).alignment = Alignment(horizontal="right")

        total_uah = kopiykas_to_uah_float(total_sum_kop)
        c_sum = ws.cell(row=curr_row, column=8, value=total_uah)
        c_sum.font = font_bold
        c_sum.alignment = Alignment(horizontal="right")
        c_sum.number_format = "#,##0.00\\ ₴"
        c_sum.fill = fill_total
        c_sum.border = thin_border

        # Auto-adjust widths
        for col in ws.columns:
            max_len = 0
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len and "\n" not in val:
                    max_len = len(val)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        ws.column_dimensions["E"].width = 36  # Counterparty name

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = "1C_Archive_Export.xlsx"
        encoded_filename = urllib.parse.quote(filename)

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
        )

    return app


app = create_app()


def main():
    """Starts the air-gapped web server on 127.0.0.1:8020."""
    import uvicorn
    print("=" * 70)
    print("1C Frozen Archive Explorer (Заморожений архів 1С/BAS)")
    print("Air-gapped server starting on http://127.0.0.1:8020")
    print("Zero-license & zero-token storage engine")
    print("=" * 70)
    uvicorn.run("one_c_frozen_archive_explorer.server:app", host="127.0.0.1", port=8020, reload=False)


if __name__ == "__main__":
    main()
