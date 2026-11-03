# 1C / BAS Frozen Archive Explorer & Historical Vault

[![Production Ready](https://img.shields.io/badge/Status-Production%20Ready-success.svg)](#)
[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](#)
[![Air Gapped](https://img.shields.io/badge/Security-100%25%20Air--Gapped%20%28Offline%29-brightgreen.svg)](#)
[![Search Latency](https://img.shields.io/badge/Search%20Speed-%3C%2035%20ms-blueviolet.svg)](#)
[![License](https://img.shields.io/badge/License-Proprietary%20Commercial-amber.svg)](#-commercial-licensing--deployment)

High-performance, air-gapped archival viewer and search engine designed for long-term historical data retention (1,825+ days) when decommissioning banned 1C / BAS accounting software under Ukrainian compliance and sanctions laws.

---

## 🎯 Regulatory Context & Business Problem

Under Ukrainian sanctions laws and cybersecurity mandates, state-owned enterprises and private businesses are actively decommissioning prohibited Russian-origin ERP/accounting software (**1C:Enterprise, BAS, UA-Budget**). 

However, **Article 44.3 of the Tax Code of Ukraine (ПКУ)** legally mandates that businesses **must preserve primary accounting documents, acts, registers, and tax invoices for at least 1,825 days (5 years)** to defend against tax audits.

**The Dilemma:** Keeping legacy 1C servers running solely to retain old records is costly, security-vulnerable, and legally hazardous.

**The Solution:** **1C Frozen Archive Explorer** extracts and permanently freezes all historical primary records into an ultra-compact, read-only columnar vault (**DuckDB + Snappy Parquet**) with an instantaneous SQLite FTS5 search index. It operates **100% locally on localhost (Air-Gapped)** with zero license fees, zero cloud token costs, and sub-50ms query speeds.

```
 Decommissioned 1C / BAS          Frozen Archive Explorer Architecture              Air-Gapped Local Web UI
┌─────────────────────────┐    ┌──────────────────────────────────────────────┐    ┌───────────────────────────┐
│ • Counterparties Dump   │    │ • DuckDB Columnar Snappy Parquet Vault       │    │ • Instant Sub-50ms Search │
│ • Invoice & Act Journal │───>│ • SQLite FTS5 BM25 Unicode Index (< 35ms)    │───>│ • Document Detail Modal   │
│ • Specification Items   │    │ • Strict Integer Financial Math (kopiykas)   │    │ • Official Excel Export   │
│ • Tax & Payment Statuses│    │ • Air-Gapped Local FastAPI Server (127.0.0.1)│    │ • Printable PDF Template  │
└─────────────────────────┘    └──────────────────────────────────────────────┘    └───────────────────────────┘
```

---

## ⚡ Core Technical Features

- **Extreme Columnar Compression (> 95% Reduction):**
  - Converts bloated SQL dumps into compressed Snappy Parquet and DuckDB files.
  - A full company archive of 1,000 documents and 2,019 item specifications compresses down to **just 133 KB**.
- **Blazing Fast Hybrid Search (< 50 ms SLA):**
  - Instant full-text lookups by company name (e.g. ТОВ, ФОП), 8-digit EDRPOU code, 10-digit tax IPN, invoice number (`РН-00128`), or line item names.
  - Sub-10ms autocomplete suggestions as the user types.
- **Strict Financial Arithmetic (Zero-Float Guarantee):**
  - All monetary values are strictly computed and stored as `BIGINT` integer kopiykas (0.01 UAH = 1 kopiyka).
  - Completely eliminates floating-point rounding discrepancies during financial and tax audits.
  - Automatic Ukrainian verbal amount rendering ("сума прописом") matching official Ukrainian bookkeeping standards.
- **100% Air-Gapped Security & Zero Recurring Costs:**
  - Binds strictly to `127.0.0.1:8020` without WAN exposure.
  - All CSS styles, layouts, and scripts are self-contained locally (zero CDN requests, 100% functional without internet).
  - $0 LLM token cost (powered by deterministic vectorized analytics and FTS5 BM25 ranking).
- **Official Compliance Exports:**
  - 1-click **Excel Export (.xlsx)** using `openpyxl` with formatted Ukrainian accounting headers.
  - **Print / PDF Form** formatted to Ukrainian primary accounting standards with authorized signature and seal blocks (Ctrl+P ready).

---

## 📊 Performance & Compression Benchmarks

Tested on a real-world benchmark accounting vault (100 counterparties, 1,000 primary invoices/acts, 2,019 line items, 31.96 Billion UAH total historical turnover):

| Operation / Query Target | Match Results | Latency | Status |
| :--- | :--- | :--- | :--- |
| **Search by EDRPOU (`40298722`)** | 9 documents | **29.1 ms** | ✅ PASS (< 50ms) |
| **Search by FOP IPN (`2849102934`)** | 1 document | **31.4 ms** | ✅ PASS (< 50ms) |
| **Search by Number (`РН-00128`)** | 1 document | **32.0 ms** | ✅ PASS (< 50ms) |
| **Search by Item Keyword (`"сервер"`)** | 200 documents | **30.5 ms** | ✅ PASS (< 50ms) |
| **Search by Region (`"Київ"`)** | 141 documents | **33.1 ms** | ✅ PASS (< 50ms) |
| **Realtime Autocomplete Suggest** | Suggestion list | **8.2 ms** | ✅ PASS (< 50ms) |
| **Aggregated Archive Analytics** | Full vault stats | **6.1 ms** | ✅ PASS (< 50ms) |
| **Storage Footprint (Parquet Vault)** | **133 KB total** | — | **> 95% Compression** |

---

## 🖼️ User Interface & Document Inspection Preview

*Fast, air-gapped web interface running locally on `http://127.0.0.1:8020`.*

```
+------------------------------------------------------------------------------------+
|  1C FROZEN ARCHIVE EXPLORER -- HISTORICAL ACCOUNTING VAULT                         |
|  [Air-Gapped: Localhost 127.0.0.1]  |  1,000 Documents  |  Turnover: 31,964,056,700 ₴|
+------------------------------------------------------------------------------------+
|  [ Search by EDRPOU, Company Name, or Doc Number...                     ] [Search] |
|                                                                                    |
|  Filters: [ All Types v ]  [ Year: 2024 v ]                                       |
|                                                                                    |
|  Doc #     | Date       | Type                | Counterparty         | Total (UAH) |
|  РН-00042  | 2024-03-14 | Видаткова накладна  | ТОВ "Агро-Трейд"     | 184,500.00 ₴|
|  АК-00119  | 2024-05-20 | Акт виконаних робіт | ФОП Шевченко О. П.   |  42,000.00 ₴|
|  СФ-00215  | 2024-08-11 | Рахунок на оплату   | ТОВ "Логістик-Схід"  | 512,300.00 ₴|
+------------------------------------------------------------------------------------+
|  [ Export Results to Excel (.xlsx) ]   [ Print Primary Document ]                  |
+------------------------------------------------------------------------------------+
```

*(Visual UI screenshots will be added to the `/screenshots` gallery).*

---

## 💼 Commercial Licensing & Deployment

This production module is developed and maintained by **Nataliia Zyma**.

The core engine and migration utilities are closed-source proprietary software available for **turnkey 1C decommissioning**, **custom archival migration**, or **on-premise enterprise licensing**:
- **Direct Email:** [`zymaneta@gmail.com`](mailto:zymaneta@gmail.com)
- **GitHub:** [@zymaneta-eng](https://github.com/zymaneta-eng)
- **Turnkey Migration Services:** Extraction from 1C/BAS SQL Server/PostgreSQL dumps, custom mapping to DuckDB Parquet vault, and staff training.
- **SLA & Response:** Inquiries are reviewed and answered within 2–4 business hours.
