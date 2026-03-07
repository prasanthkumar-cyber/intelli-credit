"""
Intelli-Credit: FastAPI Application that implements a credit decisioning engine.
Main web server with all API routes for the credit decisioning engine.
"""
import os
import io
import sys
import csv
import json
import uuid
import shutil
import sqlite3
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

import config
from databricks_client import DatabricksClient
from ingestor.document_parser import DocumentParser
from ingestor.financial_analyzer import FinancialAnalyzer
from research.web_researcher import WebResearcher
from research.insight_manager import InsightManager
from engine.decision_engine import DecisionEngine
from engine.cam_generator import CAMGenerator
from seed_demo import DEMO_ENTITIES, seed_demo_data, get_demo_entities

# ─── Initialize App ──────────────────────────────────────
app = FastAPI(title="Intelli-Credit", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ─── Initialize Components ──────────────────────────────
db = DatabricksClient()
parser = DocumentParser()
analyzer = FinancialAnalyzer()
researcher = WebResearcher()
insight_mgr = InsightManager()
decision_engine = DecisionEngine()
cam_generator = CAMGenerator()

# ─── SQLite Persistence (#12) ───────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
SQLITE_PATH = os.path.join(DATA_DIR, "intelli_credit.db")

def _get_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_sqlite():
    conn = _get_sqlite()
    conn.execute("PRAGMA journal_mode=WAL")  # Faster writes (#6)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS kv_store (
        store TEXT, entity_id TEXT, data TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (store, entity_id))""")
    conn.commit()
    conn.close()

def _sqlite_put(store: str, entity_id: str, data):
    conn = _get_sqlite()
    conn.execute("INSERT OR REPLACE INTO kv_store (store, entity_id, data, updated_at) VALUES (?,?,?,?)",
                 (store, entity_id, json.dumps(data, default=str), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def _sqlite_get(store: str, entity_id: str):
    conn = _get_sqlite()
    row = conn.execute("SELECT data FROM kv_store WHERE store=? AND entity_id=?", (store, entity_id)).fetchone()
    conn.close()
    return json.loads(row["data"]) if row else None

def _sqlite_list(store: str):
    conn = _get_sqlite()
    rows = conn.execute("SELECT entity_id, data FROM kv_store WHERE store=?", (store,)).fetchall()
    conn.close()
    return {r["entity_id"]: json.loads(r["data"]) for r in rows}

_init_sqlite()

# ─── In-memory store (fast access, backed by SQLite) ────────
_mem_store = {
    "financials": {},   # entity_id -> [records]
    "gst": {},          # entity_id -> [records]
    "cibil": {},        # entity_id -> record
    "flags": {},        # entity_id -> [flags]
    "research": {},     # entity_id -> [findings]
    "notes": {},        # entity_id -> [notes]
    "decisions": {},    # entity_id -> decision
}
_db_available = False

def _save(store: str, entity_id: str, data):
    """Save to both memory and SQLite."""
    # Ensure enum values are serialized as strings
    def _serialize(obj):
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_serialize(i) for i in obj]
        elif hasattr(obj, 'value'):  # Enum
            return obj.value
        return obj
    data = _serialize(data)
    _mem_store[store][entity_id] = data
    try:
        _sqlite_put(store, entity_id, data)
    except Exception:
        pass

def _dedup_flags(flags):
    """Remove duplicate flags based on title+category+color hash."""
    seen = set()
    unique = []
    for f in flags:
        key = (str(f.get('title', '')), str(f.get('category', '')), str(f.get('color', '')))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique

def _safe_enum_str(val):
    """Extract string from a value that might be an Enum or already a string."""
    if hasattr(val, 'value'):
        return val.value
    return str(val) if val is not None else ''

def _load_from_sqlite():
    """Load all data from SQLite into memory on startup."""
    for store in _mem_store:
        saved = _sqlite_list(store)
        for eid, data in saved.items():
            if eid not in _mem_store[store]:
                _mem_store[store][eid] = data

def _try_db(fn, *args, fallback=None, **kwargs):
    """Try Databricks, fall back to in-memory."""
    global _db_available
    if _db_available:
        try:
            return fn(*args, **kwargs)
        except Exception:
            pass
    return fallback() if callable(fallback) else fallback

def _init_db():
    global _db_available
    try:
        db.initialize_schema()
        _db_available = True
        print("[OK] Databricks connected.")
    except Exception as e:
        _db_available = False
        print(f"[WARN] Databricks offline, using in-memory mode: {e}")

# Run on startup
_init_db()
_load_from_sqlite()

# Pre-seed demo data into memory (only if not already in SQLite)
for de in DEMO_ENTITIES:
    eid = de["entity_id"]
    if eid not in _mem_store["financials"]:
        _save("financials", eid, [{**de["financials"], "company_name": de["company_name"], "entity_id": eid}])
        _save("gst", eid, [de["gst"]])
        _save("cibil", eid, de["cibil"])
        _save("flags", eid, de["flags"])
        _save("research", eid, de["research"])
        _save("notes", eid, de["notes"])

# ─── Static Files ────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ─── Root ─────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Intelli-Credit</h1>")


# ─── Database Init ────────────────────────────────────────
@app.post("/api/init-db")
async def init_database():
    """Initialize Databricks Delta tables."""
    try:
        db.initialize_schema()
        global _db_available
        _db_available = True
        return {"status": "success", "message": "All Delta tables initialized"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Demo Seed ────────────────────────────────────────────
@app.post("/api/seed-demo")
async def seed_demo():
    """Seed 3 demonstration entities (good/average/bad)."""
    try:
        if _db_available:
            seeded = seed_demo_data(use_databricks=True)
        else:
            seeded = [{"entity_id": e["entity_id"], "company_name": e["company_name"]}
                      for e in DEMO_ENTITIES]
        return {"status": "success", "seeded": seeded, "count": len(seeded)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Document Upload & Parsing ────────────────────────────
@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    entity_id: str = Form(...),
    company_name: str = Form(""),
    doc_type: str = Form("Other"),
    requested_loan_amount: float = Form(0)
):
    """Upload and parse a document."""
    try:
        os.makedirs(config.UPLOAD_DIR, exist_ok=True)
        filepath = os.path.join(config.UPLOAD_DIR, f"{entity_id}_{file.filename}")
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        parsed = parser.parse_pdf(filepath, entity_id, doc_type)
        extracted = parsed.extracted_data
        extracted["requested_loan_amount"] = requested_loan_amount

        # Save to Databricks + SQLite + memory
        _try_db(db.upsert_financials, entity_id, company_name or entity_id, doc_type, extracted)
        fin_list = _mem_store.get("financials", {}).get(entity_id, [])
        fin_list.insert(0, {**extracted, "company_name": company_name or entity_id, "entity_id": entity_id})
        _save("financials", entity_id, fin_list)

        if parsed.flags:
            flag_dicts = [f.dict() for f in parsed.flags]
            _try_db(db.save_flags, entity_id, flag_dicts)
            existing_flags = _mem_store.get("flags", {}).get(entity_id, [])
            _save("flags", entity_id, _dedup_flags(existing_flags + flag_dicts))

        if "gstr_3b_turnover" in extracted and "gstr_2a_turnover" in extracted:
            gstr_3b = float(extracted.get("gstr_3b_turnover", 0))
            gstr_2a = float(extracted.get("gstr_2a_turnover", 0))
            mismatch = abs(gstr_3b - gstr_2a) / gstr_3b * 100 if gstr_3b > 0 else 0
            circular_risk = min(mismatch * 2, 100)
            _try_db(db.save_gst_analysis, entity_id, extracted.get("period", ""),
                    gstr_3b, gstr_2a, mismatch, circular_risk)
            _save("gst", entity_id, [{"gstr_3b_turnover": gstr_3b,
                "gstr_2a_turnover": gstr_2a, "mismatch_pct": mismatch,
                "circular_trading_risk": circular_risk}])

        if "cibil_score" in extracted:
            _try_db(db.save_cibil, entity_id, extracted)
            _save("cibil", entity_id, extracted)

        return {
            "status": "success",
            "entity_id": entity_id,
            "doc_type": parsed.doc_type.value,
            "extracted_data": extracted,
            "flags": [f.dict() for f in parsed.flags],
            "filename": file.filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Manual Data Entry ────────────────────────────────────
@app.post("/api/manual-entry")
async def manual_data_entry(data: dict):
    """Manual entry of financial data when no document is available."""
    try:
        entity_id = data.get("entity_id", f"CORP_{uuid.uuid4().hex[:8].upper()}")
        company_name = data.get("company_name", entity_id)

        _try_db(db.upsert_financials, entity_id, company_name, "Manual_Entry", data)
        _save("financials", entity_id, [{**data, "company_name": company_name, "entity_id": entity_id}])

        if data.get("gstr_3b_turnover") and data.get("gstr_2a_turnover"):
            gstr_3b = float(data["gstr_3b_turnover"])
            gstr_2a = float(data["gstr_2a_turnover"])
            mismatch = abs(gstr_3b - gstr_2a) / gstr_3b * 100 if gstr_3b > 0 else 0
            circular_risk = min(mismatch * 2, 100)
            _try_db(db.save_gst_analysis, entity_id, data.get("period", "FY24"),
                    gstr_3b, gstr_2a, mismatch, circular_risk)
            _save("gst", entity_id, [{"gstr_3b_turnover": gstr_3b,
                "gstr_2a_turnover": gstr_2a, "mismatch_pct": mismatch,
                "circular_trading_risk": circular_risk}])

        if data.get("cibil_score"):
            _try_db(db.save_cibil, entity_id, data)
            _save("cibil", entity_id, data)

        analysis = analyzer.analyze(entity_id, data,
            gst_data=data if data.get("gstr_3b_turnover") else None,
            cibil_data=data if data.get("cibil_score") else None)

        flags = analysis.get("flags", [])
        if flags:
            _try_db(db.save_flags, entity_id, flags)
            existing_flags = _mem_store.get("flags", {}).get(entity_id, [])
            _save("flags", entity_id, _dedup_flags(existing_flags + flags))

        return {
            "status": "success",
            "entity_id": entity_id,
            "company_name": company_name,
            "analysis": analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Company Profile ─────────────────────────────────────
@app.get("/api/company/{entity_id}")
async def get_company(entity_id: str):
    """Get full company profile with all data."""
    try:
        financials = _try_db(db.get_financials, entity_id,
                             fallback=lambda: _mem_store["financials"].get(entity_id, []))
        gst_data = _try_db(db.get_gst_analysis, entity_id,
                           fallback=lambda: _mem_store["gst"].get(entity_id, []))
        cibil_data = _try_db(db.get_cibil, entity_id,
                             fallback=lambda: _mem_store["cibil"].get(entity_id))
        raw_flags = _try_db(db.get_flags, entity_id,
                        fallback=lambda: _mem_store["flags"].get(entity_id, []))
        research = _try_db(db.get_research, entity_id,
                           fallback=lambda: _mem_store["research"].get(entity_id, []))
        notes = _try_db(db.get_notes, entity_id,
                        fallback=lambda: _mem_store["notes"].get(entity_id, []))
        decision = _try_db(db.get_decision, entity_id,
                           fallback=lambda: _mem_store["decisions"].get(entity_id))

        # BUG 2: Deduplicate flags
        # BUG 3: Filter out Web Research flags from risk flags panel
        clean_flags = _dedup_flags(raw_flags or [])
        clean_flags = [f for f in clean_flags
                       if f.get('source_type') != 'Research'
                       and not str(f.get('source', '')).startswith('Web Research')]

        return {
            "entity_id": entity_id,
            "financials": financials or [],
            "gst_analysis": gst_data or [],
            "cibil_data": cibil_data,
            "flags": clean_flags,
            "research_findings": research or [],
            "officer_notes": notes or [],
            "decision": decision
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/company/summary/{entity_id}")
async def get_company_summary(entity_id: str):
    """Get lightweight company profile for fast dashboard loading."""
    try:
        financials = _try_db(db.get_financials, entity_id,
                             fallback=lambda: _mem_store["financials"].get(entity_id, []))
        gst_data = _try_db(db.get_gst_analysis, entity_id,
                           fallback=lambda: _mem_store["gst"].get(entity_id, []))
        cibil_data = _try_db(db.get_cibil, entity_id,
                             fallback=lambda: _mem_store["cibil"].get(entity_id))
        decision = _try_db(db.get_decision, entity_id,
                           fallback=lambda: _mem_store["decisions"].get(entity_id))

        return {
            "entity_id": entity_id,
            "financials": financials or [],
            "gst_analysis": gst_data or [],
            "cibil_data": cibil_data,
            "decision": decision
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Research ─────────────────────────────────────────────
@app.post("/api/research/{entity_id}")
async def run_research(entity_id: str, data: dict = None):
    """Trigger web research for a company."""
    try:
        data = data or {}
        company_name = data.get("company_name", entity_id)
        promoters = data.get("promoters", [])
        sector = data.get("sector")
        location = data.get("location")

        findings = researcher.research_company(
            company_name, entity_id, promoters, sector, location
        )

        finding_dicts = [f.dict() for f in findings]
        _try_db(db.save_research, entity_id, finding_dicts)
        _save("research", entity_id, finding_dicts)

        all_flags = []
        for f in findings:
            for fl in f.flags:
                fd = fl.dict()
                fd["source_type"] = "Research"
                all_flags.append(fd)
        # BUG 3: Do NOT save research flags to main flags table
        # They go to research_flags store only, and appear in Decision Rationale
        if all_flags:
            if "research_flags" not in _mem_store:
                _mem_store["research_flags"] = {}
            existing_research = _mem_store.get("research_flags", {}).get(entity_id, [])
            _mem_store["research_flags"][entity_id] = _dedup_flags(existing_research + all_flags)

        return {
            "status": "success",
            "entity_id": entity_id,
            "findings_count": len(findings),
            "findings": finding_dicts,
            "flags": all_flags
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Credit Officer Notes ────────────────────────────────
@app.post("/api/notes/preview")
async def preview_note(data: dict):
    """Preview category and severity before submitting note."""
    try:
        note_text = data.get("note", "")
        # Use existing manager logic without saving
        processed = insight_mgr.process_note(note_text, "Preview", "Preview", None)
        return {
            "status": "success",
            "category": _safe_enum_str(processed.category),
            "severity": processed.severity
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/notes/{entity_id}")
async def add_note(entity_id: str, data: dict):
    """Add a credit officer's qualitative note."""
    try:
        note_text = data.get("note", "")
        officer_name = data.get("officer_name", "Credit Officer")
        category = data.get("category", None)

        processed = insight_mgr.process_note(note_text, entity_id,
                                              officer_name, category)

        note_dict = processed.dict()
        _try_db(db.save_note, entity_id, note_dict)
        saved_note = {
            "note": note_text, "officer_name": officer_name,
            "category": _safe_enum_str(processed.category),
            "severity": processed.severity,
            "created_at": datetime.utcnow().isoformat()
        }
        existing_notes = _mem_store.get("notes", {}).get(entity_id, [])
        _save("notes", entity_id, existing_notes + [saved_note])

        if processed.flags:
            flag_dicts = [f.dict() for f in processed.flags]
            _try_db(db.save_flags, entity_id, flag_dicts)
            existing_flags = _mem_store.get("flags", {}).get(entity_id, [])
            _save("flags", entity_id, _dedup_flags(existing_flags + flag_dicts))

        return {
            "status": "success",
            "entity_id": entity_id,
            "severity": processed.severity,
            "category": _safe_enum_str(processed.category),
            "flags": [f.dict() for f in processed.flags],
            "saved_note": saved_note
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Notes History ────────────────────────────────────────
@app.get("/api/notes/{entity_id}")
async def get_notes_history(entity_id: str):
    """Get chronological list of all notes for an entity."""
    try:
        notes = _try_db(db.get_notes, entity_id,
                        fallback=lambda: _mem_store["notes"].get(entity_id, []))
        return {"status": "success", "entity_id": entity_id, "notes": notes or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Credit Analysis & Decision ──────────────────────────
@app.get("/api/analyze/{entity_id}")
async def analyze_and_decide(entity_id: str):
    """Run full XGBoost analysis and generate credit decision."""
    try:
        financials_list = _try_db(db.get_financials, entity_id,
                                  fallback=lambda: _mem_store["financials"].get(entity_id, []))
        gst_data = _try_db(db.get_gst_analysis, entity_id,
                           fallback=lambda: _mem_store["gst"].get(entity_id, []))
        cibil_data = _try_db(db.get_cibil, entity_id,
                             fallback=lambda: _mem_store["cibil"].get(entity_id))
        raw_flags = _try_db(db.get_flags, entity_id,
                        fallback=lambda: _mem_store["flags"].get(entity_id, []))
        notes = _try_db(db.get_notes, entity_id,
                        fallback=lambda: _mem_store["notes"].get(entity_id, []))

        if not financials_list:
            raise HTTPException(status_code=404,
                              detail="No financial data found for this entity. Please enter data first via Data Ingestor.")

        fin = financials_list[0]
        company_name = fin.get("company_name", entity_id)

        gst_dict = gst_data[0] if gst_data else None
        analysis = analyzer.analyze(entity_id, fin, gst_dict, cibil_data)

        analysis_flags = analysis.get("flags", [])
        # BUG 2+3: Dedup AND filter out Web Research flags from risk scoring
        combined_flags = _dedup_flags((raw_flags or []) + analysis_flags)
        all_flags = [f for f in combined_flags
                     if f.get('source_type') != 'Research'
                     and not str(f.get('source', '')).startswith('Web Research')]

        # Include research flags in decision rationale only, not risk scoring
        research_flags = _mem_store.get("research_flags", {}).get(entity_id, [])

        features = analyzer.compute_feature_inputs(fin, gst_dict, cibil_data, all_flags)

        if notes:
            features["officer_severity_score"] = insight_mgr.compute_severity_score(notes)

        try:
            decision = decision_engine.make_decision(
                entity_id, company_name, features, all_flags, fin
            )
        except Exception as model_err:
            # XGBoost error handling (#3)
            import traceback
            tb = traceback.format_exc()
            print(f"[ERROR] XGBoost analysis failed for {entity_id}: {model_err}")
            print(tb)
            raise HTTPException(
                status_code=500,
                detail=f"Analysis engine error: {str(model_err)}. Check server logs for full traceback."
            )

        decision_dict = decision.dict()
        five_cs = {
            "character": decision.five_cs.character,
            "capacity": decision.five_cs.capacity,
            "capital": decision.five_cs.capital,
            "collateral": decision.five_cs.collateral,
            "conditions": decision.five_cs.conditions,
        }
        decision_dict["five_cs"] = five_cs
        decision_dict["character_score"] = five_cs["character"]
        decision_dict["capacity_score"] = five_cs["capacity"]
        decision_dict["capital_score"] = five_cs["capital"]
        decision_dict["collateral_score"] = five_cs["collateral"]
        decision_dict["conditions_score"] = five_cs["conditions"]

        # BUG 6: Three-tier decision mapping BEFORE saving to store
        decision_label = decision.decision
        risk = decision.risk_score
        if decision_label == "APPROVED" and (decision.confidence < 0.7 or 30 <= risk <= 65):
            decision_label = "CONDITIONAL"

        # Generate specific conditions for CONDITIONAL
        conditions = []
        if decision_label == "CONDITIONAL":
            if features.get("collateral_coverage", 0) < 1.5:
                conditions.append("Additional collateral required to achieve 1.5x coverage")
            if features.get("cibil_score", 0) < 700:
                conditions.append("Personal guarantee from promoter required")
            if features.get("gstr_mismatch_pct", 0) > 10:
                conditions.append("Quarterly GST reconciliation review mandated")
            if features.get("debt_equity_ratio", 0) > 2:
                conditions.append("Debt reduction plan within 12 months")
            if features.get("officer_severity_score", 0) > 40:
                conditions.append("Follow-up site visit within 90 days")
            if not conditions:
                conditions.append("Enhanced monitoring with quarterly reporting")
                conditions.append("Review after 6 months based on financial performance")

        # Update decision_dict with final label + conditions BEFORE saving
        decision_dict["decision"] = decision_label
        decision_dict["conditions"] = conditions
        decision_dict["requested_loan_amount"] = float(fin.get("requested_loan_amount", 0))

        if decision_label == "CONDITIONAL" and decision_dict.get("recommended_loan_amount"):
            # Apply haircut to memory object before saving so Dashboard sees it
            decision_dict["recommended_loan_amount"] = round(decision_dict["recommended_loan_amount"] * 0.75, 2)

        _try_db(db.save_decision, decision_dict)
        _save("decisions", entity_id, decision_dict)

        # Audit Trail Logging
        try:
            audit_file = os.path.join(config.REPORTS_DIR, "audit_log.csv")
            file_exists = os.path.isfile(audit_file)
            with open(audit_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Timestamp", "Entity ID", "Action", "User", "Decision", "Risk Score"])
                writer.writerow([
                    datetime.utcnow().isoformat(),
                    entity_id,
                    "RUN_ANALYSIS",
                    "System_User",  # Can wire to real auth later
                    decision_label,
                    decision.risk_score
                ])
        except Exception as audit_err:
            print(f"[WARN] Failed to write audit log: {audit_err}")

        return {
            "status": "success",
            "entity_id": entity_id,
            "company_name": company_name,
            "decision": decision_label,
            "conditions": conditions,
            "confidence": decision.confidence,
            "risk_score": decision.risk_score,
            "recommended_loan_amount": decision.recommended_loan_amount,
            "requested_loan_amount": float(fin.get("requested_loan_amount", 0)),
            "recommended_interest_rate": decision.recommended_interest_rate,
            "five_cs": five_cs,
            "shap_explanations": decision.shap_explanations,
            "decision_reasons": decision.decision_reasons + \
                [f"Research: {rf.get('title', '')}" for rf in research_flags[:5]],
            "all_flags": [f if isinstance(f, dict) else f.dict()
                         for f in decision.all_flags],
            "feature_values": features,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── CAM Generation ──────────────────────────────────────
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import uuid

@app.get("/api/cam/pdf/{entity_id}")
async def generate_cam_pdf(entity_id: str):
    """Generate Credit Appraisal Memo (PDF document)."""
    try:
        decision = _try_db(db.get_decision, entity_id,
                           fallback=lambda: _mem_store["decisions"].get(entity_id))
        
        if not decision:
            raise HTTPException(status_code=400, detail="Run analysis first before generating CAM")
            
        financials_list = _try_db(db.get_financials, entity_id, fallback=lambda: _mem_store["financials"].get(entity_id, []))
        fin = financials_list[0] if financials_list else {}

        filename = f"CAM_{entity_id}_{uuid.uuid4().hex[:6]}.pdf"
        filepath = os.path.join(config.REPORTS_DIR, filename)
        os.makedirs(config.REPORTS_DIR, exist_ok=True)

        c = canvas.Canvas(filepath, pagesize=letter)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, "Intelli-Credit: Credit Appraisal Memo (PDF)")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 720, f"Entity ID: {entity_id}")
        c.drawString(50, 700, f"Company Name: {fin.get('company_name', entity_id)}")
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 660, "Decision Details")
        c.setFont("Helvetica", 12)
        c.drawString(50, 640, f"Status: {decision.get('decision', 'N/A')}")
        c.drawString(50, 620, f"Risk Score: {decision.get('risk_score', 'N/A')}/100")
        c.drawString(50, 600, f"Requested Loan: {fin.get('requested_loan_amount', 0)}")
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 560, "Decision Rationale")
        c.setFont("Helvetica", 10)
        
        y = 540
        reasons = decision.get("decision_reasons", [])
        if isinstance(reasons, str):
            try: reasons = json.loads(reasons)
            except: reasons = [reasons]
            
        for r in reasons[:5]:
            c.drawString(50, y, f"- {r[:100]}...")
            y -= 20
            
        c.save()

        return FileResponse(
            filepath,
            media_type="application/pdf",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cam/{entity_id}")
async def generate_cam(entity_id: str):
    """Generate Credit Appraisal Memo (Word document)."""
    try:
        financials_list = _try_db(db.get_financials, entity_id,
                                  fallback=lambda: _mem_store["financials"].get(entity_id, []))
        gst_data = _try_db(db.get_gst_analysis, entity_id,
                           fallback=lambda: _mem_store["gst"].get(entity_id, []))
        cibil_data = _try_db(db.get_cibil, entity_id,
                             fallback=lambda: _mem_store["cibil"].get(entity_id))
        flags = _try_db(db.get_flags, entity_id,
                        fallback=lambda: _mem_store["flags"].get(entity_id, []))
        research = _try_db(db.get_research, entity_id,
                           fallback=lambda: _mem_store["research"].get(entity_id, []))
        notes = _try_db(db.get_notes, entity_id,
                        fallback=lambda: _mem_store["notes"].get(entity_id, []))
        decision = _try_db(db.get_decision, entity_id,
                           fallback=lambda: _mem_store["decisions"].get(entity_id))

        if not decision:
            raise HTTPException(status_code=400,
                              detail="Run analysis first before generating CAM")

        fin = financials_list[0] if financials_list else {}
        gst_dict = gst_data[0] if gst_data else None

        if isinstance(decision.get("shap_explanations"), str):
            try:
                decision["shap_explanations"] = json.loads(decision["shap_explanations"])
            except:
                decision["shap_explanations"] = {}
        if isinstance(decision.get("decision_reasons"), str):
            try:
                decision["decision_reasons"] = json.loads(decision["decision_reasons"])
            except:
                decision["decision_reasons"] = []

        if "character_score" in decision:
            decision["five_cs"] = {
                "character": decision.get("character_score", 50),
                "capacity": decision.get("capacity_score", 50),
                "capital": decision.get("capital_score", 50),
                "collateral": decision.get("collateral_score", 50),
                "conditions": decision.get("conditions_score", 50),
            }

        filepath = cam_generator.generate(
            decision_data=decision, financials=fin, gst_data=gst_dict,
            cibil_data=cibil_data, research_findings=research,
            officer_notes=notes, flags=flags
        )

        return FileResponse(
            filepath,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=os.path.basename(filepath)
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Entity Listing (with search) ────────────────────────
@app.get("/api/entities")
async def list_entities(q: str = ""):
    """List all entities, optionally filtered by search query."""
    try:
        # Combine DB + memory entities
        entities = []
        seen = set()

        # Memory store first (always available)
        for eid, recs in _mem_store["financials"].items():
            if eid not in seen:
                name = recs[0].get("company_name", eid) if recs else eid
                entities.append({"entity_id": eid, "company_name": name})
                seen.add(eid)

        # Try DB
        if _db_available:
            try:
                db_entities = db.list_entities()
                for e in db_entities:
                    if e.get("entity_id") not in seen:
                        entities.append(e)
                        seen.add(e["entity_id"])
            except:
                pass

        # Filter by search query
        if q:
            q_lower = q.lower()
            entities = [e for e in entities
                       if q_lower in e.get("entity_id", "").lower()
                       or q_lower in e.get("company_name", "").lower()]

        return {"entities": entities}
    except Exception as e:
        return {"entities": [], "error": str(e)}


# ─── Batch CSV Upload ────────────────────────────────────
@app.post("/api/batch-upload")
async def batch_csv_upload(file: UploadFile = File(...)):
    """Upload a CSV file with multiple entities for bulk assessment."""
    try:
        content = await file.read()
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))

        results = []
        for row in reader:
            eid = row.get("entity_id", f"BATCH_{uuid.uuid4().hex[:6].upper()}")
            name = row.get("company_name", eid)

            # Convert numeric fields
            data = {"entity_id": eid, "company_name": name}
            numeric_fields = ["revenue", "ebitda", "net_profit", "total_debt",
                            "total_assets", "net_worth", "current_assets",
                            "current_liabilities", "collateral_value",
                            "interest_expense", "operating_margin",
                            "revenue_growth_yoy", "gstr_3b_turnover",
                            "gstr_2a_turnover", "cibil_score", "overdue_accounts",
                            "suit_filed_accounts", "dpd_90_plus",
                            "credit_utilization_pct", "requested_loan_amount"]
            for field in numeric_fields:
                val = row.get(field, "")
                if val:
                    try:
                        data[field] = float(val)
                    except ValueError:
                        results.append({
                            "entity_id": eid, "company_name": name,
                            "status": "error",
                            "error": f"Invalid value '{val}' for field '{field}'"
                        })
                        continue

            # Save
            _try_db(db.upsert_financials, eid, name, "CSV_Batch", data)
            _save("financials", eid, [{**data, "company_name": name, "entity_id": eid}])

            if data.get("gstr_3b_turnover") and data.get("gstr_2a_turnover"):
                gstr_3b = data["gstr_3b_turnover"]
                gstr_2a = data["gstr_2a_turnover"]
                mismatch = abs(gstr_3b - gstr_2a) / gstr_3b * 100 if gstr_3b > 0 else 0
                _save("gst", eid, [{"gstr_3b_turnover": gstr_3b,
                    "gstr_2a_turnover": gstr_2a, "mismatch_pct": mismatch,
                    "circular_trading_risk": min(mismatch * 2, 100)}])

            if data.get("cibil_score"):
                _save("cibil", eid, data)

            results.append({"entity_id": eid, "company_name": name, "status": "loaded"})

        return {
            "status": "success",
            "entities_loaded": len(results),
            "results": results
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid CSV encoding. Please use UTF-8.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Workflow Progress ────────────────────────────────────
@app.get("/api/progress/{entity_id}")
async def get_progress(entity_id: str):
    """Get workflow progress for an entity."""
    fin = _mem_store["financials"].get(entity_id, [])
    gst = _mem_store["gst"].get(entity_id, [])
    cibil = _mem_store["cibil"].get(entity_id)
    flags = _mem_store["flags"].get(entity_id, [])
    research = _mem_store["research"].get(entity_id, [])
    notes = _mem_store["notes"].get(entity_id, [])
    decision = _mem_store["decisions"].get(entity_id)

    steps = {
        "data_ingested": len(fin) > 0,
        "gst_analyzed": len(gst) > 0 or bool(cibil),
        "research_done": len(research) > 0,
        "notes_added": len(notes) > 0,
        "analyzed": decision is not None,
        "report_ready": decision is not None,
    }
    completed = sum(1 for v in steps.values() if v)
    total = len(steps)

    return {
        "entity_id": entity_id,
        "steps": steps,
        "completed": completed,
        "total": total,
        "percent": int(completed / total * 100)
    }


# ─── Circular Trading Check ──────────────────────────────
@app.get("/api/circular-trading/{entity_id}")
async def check_circular_trading(entity_id: str):
    """Run circular trading detection."""
    try:
        result = _try_db(db.detect_circular_trading, entity_id,
                         fallback=lambda: {"risk_level": "unknown", "details": "Databricks offline"})
        return {"status": "success", **(result or {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── CSV Template Download (#11) ─────────────────────────
@app.get("/api/csv-template")
async def csv_template():
    """Download a CSV template for batch upload."""
    headers = ["entity_id","company_name","revenue","ebitda","net_profit",
               "total_debt","total_assets","net_worth","current_assets",
               "current_liabilities","collateral_value","interest_expense",
               "operating_margin","revenue_growth_yoy","gstr_3b_turnover",
               "gstr_2a_turnover","cibil_score","overdue_accounts",
               "suit_filed_accounts","dpd_90_plus","credit_utilization_pct",
               "requested_loan_amount"]
    sample = ["CORP_001","Acme Corp","100000000","20000000","15000000",
              "25000000","120000000","60000000","40000000","20000000",
              "50000000","3000000","20","12","95000000","92000000",
              "750","0","0","0","45","20000000"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerow(sample)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=intelli_credit_template.csv"}
    )


# ─── Health Check ────────────────────────────────────────
@app.get("/api/health")
async def health():
    db_read = "offline"
    db_write = "offline"
    if _db_available:
        # Test read
        try:
            db.list_entities()
            db_read = "connected"
        except Exception:
            db_read = "error"
        # Test write (schema check)
        try:
            db._execute(f"SELECT 1 FROM {db._table('corporate_financials')} LIMIT 1", fetch=True)
            db_write = "connected"
        except Exception:
            db_write = "error"
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "databricks_read": db_read,
        "databricks_write": db_write,
        "databricks": "connected" if _db_available else "offline (in-memory mode)",
        "persistence": "sqlite",
        "demo_entities": len(DEMO_ENTITIES)
    }
