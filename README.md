# 1C / BAS Frozen Archive Explorer & Historical Vault

[![Production Ready](https://img.shields.io/badge/Status-Production%20Ready-success.svg)](#)
[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](#)
[![Air Gapped](https://img.shields.io/badge/Security-100%25%20Air--Gapped%20%28Offline%29-brightgreen.svg)](#)
[![Search Latency](https://img.shields.io/badge/Search%20Speed-%3C%2035%20ms-blueviolet.svg)](#)
[![WORM Audit](https://img.shields.io/badge/Integrity-SHA--256%20WORM%20Verified-blue.svg)](#)
[![License](https://img.shields.io/badge/License-Proprietary%20Commercial-amber.svg)](#-commercial-licensing--deployment)

High-performance, air-gapped archival viewer, reconciliation engine, and full-text search platform designed for long-term historical data retention (1,825+ days) when decommissioning banned 1C / BAS accounting software under Ukrainian compliance and sanctions laws.

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
│ • Multi-Org Ledgers     │───>│ • SQLite FTS5 BM25 Unicode Index (< 35ms)    │───>│ • Multi-Entity Switcher   │
│ • Invoice & Act Journal │    │ • Strict Integer Financial Math (kopiykas)   │    │ • Reconciliation Act View │
│ • Specification Items   │    │ • SHA-256 Cryptographic WORM Manifest        │    │ • Official Excel Export   │
│ • Tax & Payment Statuses│    │ • Air-Gapped Local FastAPI Server (127.0.0.1)│    │ • Printable PDF Template  │
└─────────────────────────┘    └──────────────────────────────────────────────┘    └───────────────────────────┘
```

---

## ⚡ Core Technical & Enterprise Features

- **Extreme Columnar Compression (> 95% Reduction):**
  - Converts bloated SQL dumps into compressed Snappy Parquet and DuckDB files.
  - A full enterprise archive of 1,000 documents and 1,409 item specifications compresses down to **just 111 KB in Parquet**.
- **Multi-Organization Enterprise Support (Multi-Entity):**
  - Built-in multi-company selector (`ТОВ "Ареонікс Діджитал"`, `ФОП Мельник В.О.`, or consolidated holding view).
  - Dynamic real-time recalculation of turnover, document counts, and counterparty balances per legal entity.
- **Bilateral Reconciliation Act (Акт звірки взаєморозрахунків):**
  - 1-click generation of official mutual reconciliation statements between our organization and any counterparty.
  - Debit/Credit transactions computed in exact `BIGINT` kopiykas with dual-column accounting ledgers.
  - Full Ukrainian verbal debt expression ("сума прописом") and official printable format ready for director/accountant signatures and seals.
- **Cryptographic WORM Audit Manifest (SHA-256 Bit-Level Integrity):**
  - Complies with TCU Art. 44.3 requirements for immutable data retention.
  - Computes and verifies SHA-256 hash of `archive_vault.duckdb` with live in-browser verification ensuring zero data tampering.
- **Blazing Fast Hybrid Search (< 50 ms SLA):**
  - Instant full-text lookups by counterparty name (e.g. ТОВ, ФОП), 8-digit EDRPOU code, 10-digit tax IPN, invoice number (`РН-00128`), or line item names.
  - Sub-10ms autocomplete suggestions as the user types.
- **Strict Financial Arithmetic (Zero-Float Guarantee):**
  - All monetary values are strictly computed and stored as `BIGINT` integer kopiykas (0.01 UAH = 1 kopiyka).
  - Completely eliminates floating-point rounding discrepancies during financial and tax audits.
- **100% Air-Gapped Security & Zero Recurring Costs:**
  - Binds strictly to `127.0.0.1:8020` without WAN exposure.
  - All CSS styles, layouts, and scripts are self-contained locally (zero CDN requests, 100% functional without internet).
  - $0 LLM token cost (powered by deterministic vectorized analytics and FTS5 BM25 ranking).
- **Official Compliance Exports:**
  - **Filtered Excel Export (.xlsx)** preserving all active search and organization filters with formatted accounting headers.
  - **Print / PDF Form** formatted to Ukrainian primary accounting standards with authorized signature and seal blocks (Ctrl+P ready).

---

## 📊 Performance & Compression Benchmarks

Tested on a benchmark enterprise vault (100 counterparties, 1,000 primary invoices/acts, 1,409 line items, 48.80 Million UAH total historical turnover):

| Operation / Query Target | Match Results | Latency | Status |
| :--- | :--- | :--- | :--- |
| **Search by EDRPOU (`38491023`)** | 1 document | **24.2 ms** | ✅ PASS (< 50ms) |
| **Search by FOP IPN (`2849102934`)** | 1 document | **26.1 ms** | ✅ PASS (< 50ms) |
| **Search by Number (`РН-00128`)** | 1 document | **22.5 ms** | ✅ PASS (< 50ms) |
| **Search by Item Keyword (`"сервер"`)** | 185 documents | **28.3 ms** | ✅ PASS (< 50ms) |
| **Reconciliation Act Generation** | Full ledger | **14.8 ms** | ✅ PASS (< 50ms) |
| **Realtime Autocomplete Suggest** | Suggestion list | **6.4 ms** | ✅ PASS (< 50ms) |
| **Aggregated Archive Analytics** | Full vault stats | **4.9 ms** | ✅ PASS (< 50ms) |
| **Storage Footprint (Parquet Vault)** | **111 KB total** | — | **> 95% Compression** |

---

## 🖼️ User Interface & Document Inspection Preview

*Fast, air-gapped web interface running locally on `http://127.0.0.1:8020`.*

```
+----------------------------------------------------------------------------------------------------+
|  [🧊] 1C FROZEN ARCHIVE EXPLORER -- HISTORICAL ACCOUNTING VAULT             [🛡️ Сертифікат WORM]   |
|  [Air-Gapped: 127.0.0.1:8020]  |  1,000 Documents  |  Turnover: 48,802,871.00 ₴ (BIGINT)           |
+----------------------------------------------------------------------------------------------------+
|  Організація: [ ТОВ "Ареонікс Діджитал" (ЄДРПОУ: 43981245) ▾ ]                                    |
|  Пошук: [ Введіть назву, ЄДРПОУ або номер...                              ] [🔍 Шукати]            |
|                                                                                                    |
|  Фільтри: [ Всі типи ▾ ]  [ Всі роки ▾ ]                                                           |
|                                                                                                    |
|  №       | Організація       | Тип        | Номер    | Дата       | Контрагент          | Сума (грн)   |
|  1       | Ареонікс Діджитал | Видаткова  | РН-00042 | 14.03.2024 | ТОВ "Агро-Трейд"    |  78,782.00 ₴ |
|  2       | ФОП Мельник В.О.  | Акт робіт  | АК-00119 | 20.05.2024 | ФОП Шевченко О. П.  |  24,954.00 ₴ |
+----------------------------------------------------------------------------------------------------+
|  [📥 Експорт в Excel (.xlsx)]   [📋 Акт звірки взаєморозрахунків]   [🖨️ Друк первинного документа]  |
+----------------------------------------------------------------------------------------------------+
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
