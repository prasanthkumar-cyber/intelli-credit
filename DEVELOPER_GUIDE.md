# Intelli-Credit Developer Guide

Welcome to the Intelli-Credit codebase! This document provides a comprehensive overview of the system architecture, directory structure, data flow, and key files. Use this guide to understand how the application works, how to modify it, or how to onboard new developers.

---

## 🏗️ Architecture Overview

Intelli-Credit is an AI-powered credit decisioning web application. It automates financial parsing, NLP-based officer notes analysis, and machine learning credit scoring.

- **Frontend**: Vanilla JavaScript (`app.js`), HTML5, and CSS3. It operates as a Single-Page Application (SPA) utilizing `fetch` for API communication and `Chart.js` for data visualization (Radar charts, SHAP waterfall charts).
- **Backend API**: Python 3 with **FastAPI**. It handles routing, data validation, and connects the frontend to the ML pipelines.
- **Machine Learning**: **XGBoost** for risk scoring and **SHAP** (SHapley Additive exPlanations) for transparent, explainable feature contributions.
- **Data Persistence**: A multi-tiered storage approach:
  1. **In-Memory Cache**: Fast reads for active sessions.
  2. **SQLite**: Local fallback storage (`data/intelli_credit.db`).
  3. **Databricks Delta Tables**: Primary enterprise storage (via `databricks_client.py`).

---

## 📂 Directory Structure & Core Files

### 1. Root Directory (Backend Core)
The root directory contains the FastAPI server, configuration, and data models.

*   **`app.py`**: The main entry point. Initializes the FastAPI application, mounts the static frontend, and defines all REST API endpoints (e.g., `/api/company/{id}`, `/api/analyze`, `/api/upload`). It also houses the Databricks/SQLite fallback logic (`_try_db`).
*   **`models.py`**: Contains **Pydantic** models. This is the source of truth for data structures (e.g., `RiskFlag`, `GSTAnalysis`, `CIBILData`, `ParsedDocument`). Modifying database schemas or API payloads starts here.
*   **`config.py`**: Environment variable loading and global constants (e.g., model paths, API keys, Databricks connection strings).
*   **`databricks_client.py`**: Manages the connection pool and SQL execution for Databricks Delta Tables.

### 2. Frontend (`static/`)
The user interface is entirely contained within the `static` folder.

*   **`index.html`**: The single HTML file. Contains the markup for all application "views" (Dashboard, Analysis, Compare, Notes, Ingestor) which are toggled via CSS classes.
*   **`styles.css`**: Vanilla CSS handling layout (CSS Grid/Flexbox), component styling, theming, and responsive design.
*   **`app.js`**: The brains of the frontend. It manages:
    *   **Global State**: `window.intelliCreditState` (tracks the currently loaded entity, name, and decision across tabs).
    *   **Routing**: Tab switching logic (`openTab`).
    *   **API Calls**: Asynchronous `fetch` calls to the FastAPI backend (e.g., `loadCompany()`, `runAnalysis()`). 
    *   **Rendering**: Painting data into the DOM (e.g., `renderDashboard`, `renderFlags`). Contains specific handling for formatting numbers (`formatLoanAmount`, `formatDSCR`) and preventing data-race conditions using `AbortController`.

### 3. ML & Decisioning (`engine/`)
The computational core for generating risk scores and credit limit recommendations.

*   **`decision_engine.py`**: Houses the `DecisionEngine` class. It orchestrates the XGBoost model predictions, maps continuous risk scores (0-100) into discrete categories (`APPROVED`, `CONDITIONAL`, `REJECTED`), and calculates the `recommended_loan_amount` using financial multi-tier rules and haircuts.
*   **`credit_model.py`**: Handles loading the pre-trained XGBoost `.json` model, feature engineering, and computing SHAP arrays for explainability.
*   **`cam_generator.py`**: Handles generating downloadable Credit Appraisal Memos (CAM). Uses `python-docx` for Word documents and `reportlab` for PDF generation.

### 4. Data Extraction (`ingestor/`)
Responsible for parsing incoming raw data into structured financial signals.

*   **`document_parser.py`**: Parses uploaded documents (PDFs, bank statements, GST filings). It features logic to detect text, tables, and red-flag keywords.
*   **`financial_analyzer.py`**: Computes derived financial ratios (e.g., DSCR, D/E Ratio, EBITDA margin) from the raw ingested tabular data.

### 5. Research & NLP (`research/`)
Analyzes qualitative (text) data streams.

*   **`insight_manager.py`**: Contains the NLP keyword weighting dictionary (`CATEGORY_KEYWORDS`, `SEVERITY_RULES`). It processes Credit Officer Notes, automatically detecting if a note is "Operations", "Legal", "Market", etc., and assigns a severity tier (Low/Medium/High/Critical) based on the presence of high-risk operational terms.
*   **`web_researcher.py`**: Handles simulated or live web scraping/enrichment for company promoters against public databases or news sources.

---

## 🔄 How Data Flows (Example: Loading an Entity)

1.  **User Action**: The user enters an Entity ID (e.g., `V5_GOOD`) in the Dashboard UI and clicks "Load".
2.  **Frontend (app.js)**: 
    *   `loadCompany()` is triggered. It immediately locks `window.currentLoadedEntity = id;` to prevent race conditions.
    *   It calls the lightweight `/api/company/summary/{id}` to paint the screen instantly.
    *   It simultaneously launches `fetchRiskFlags(id)` into the background using an `AbortController` to cancel any previously flighted requests.
3.  **Backend (app.py)**: The FastAPI `@app.get("/api/company/{entity_id}")` endpoint fires. It attempts to read from Databricks via `db.get_financials()`; if offline, it falls back to the SQLite dictionary (`_try_db()`). 
4.  **Transformation**: Pydantic models (`models.py`) serialize Enums and clean the flags dictionary.
5.  **Rendering**: `app.js` receives the full JSON payload, updates Chart.js canvases (Radar, SHAP), and maps HTML elements to display the newly calculated loan amount (formatted back to Crores/Lakhs).

---

## 🛠️ Modifying the Application

### Adding a New Financial Metric
To add a new metric (e.g., 'Inventory Turnover'):
1.  **Backend (`models.py`)**: Add the field to the `ParsedDocument` or relevant base model schema.
2.  **Calculations (`ingestor/financial_analyzer.py`)**: Add the math to compute the new metric from raw inputs.
3.  **Engine (`engine/decision_engine.py`)**: If this metric should impact the ML model or the loan amount, update `_calculate_loan_amount` or append it to the `features` dictionary generated for XGBoost.
4.  **Frontend (`static/index.html` & `app.js`)**: Add a new `<div class="info-item">` to the Dashboard Grid and populate it via JavaScript inside `renderDashboard()`.

### Adjusting NLP Note Severity
If credit officers complain that certain words are heavily penalizing a company's risk score inadvertently:
- Open `research/insight_manager.py`.
- Adjust `SEVERITY_RULES` or remove the offending word from the `CATEGORY_KEYWORDS` dictionary. The application relies on a weighted bag-of-words approach to auto-escalate severities.

### Updating Loan Amount Rules
If the business decides to cap CONDITIONAL approvals at 50% instead of 75%:
- Open `app.py`.
- Locate the `analyze_and_decide` route (near line ~597).
- Find the conditional modifier: `decision_dict["recommended_loan_amount"] * 0.75` and change it to `0.50`.
- Verify the base generation logic inside `engine/decision_engine.py` -> `_calculate_loan_amount()`.
