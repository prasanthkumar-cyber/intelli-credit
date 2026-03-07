"""
Intelli-Credit Configuration
Centralized environment configuration for the credit decisioning engine.
"""
import os
from dotenv import load_dotenv

# Load .env from project root or venv
for env_path in ["venv/.env", ".env"]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

# ─── Databricks ──────────────────────────────────────────
DATABRICKS_SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
DATABRICKS_CATALOG = os.getenv("DATABRICKS_CATALOG", "fingen")
DATABRICKS_SCHEMA = os.getenv("DATABRICKS_SCHEMA", "default")

# ─── SerpAPI (Web Research) ──────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# ─── XGBoost Model ──────────────────────────────────────
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
CLASSIFIER_PATH = os.path.join(MODEL_DIR, "credit_classifier.json")
REGRESSOR_PATH = os.path.join(MODEL_DIR, "risk_regressor.json")

# ─── Thresholds ─────────────────────────────────────────
GST_MISMATCH_RED_THRESHOLD = 0.20      # 20% mismatch = red flag
GST_MISMATCH_BLUE_THRESHOLD = 0.10     # 10% mismatch = blue flag
CIBIL_RED_THRESHOLD = 600
CIBIL_GREEN_THRESHOLD = 750
DSCR_RED_THRESHOLD = 1.0
DSCR_GREEN_THRESHOLD = 2.0
DEBT_EQUITY_RED_THRESHOLD = 3.0
DEBT_EQUITY_GREEN_THRESHOLD = 1.5

# ─── Risk Premium & Loan Calc ──────────────────────────
BASE_INTEREST_RATE = 9.0    # Base rate %
MAX_RISK_PREMIUM = 6.0      # Maximum risk premium %
MAX_LTV_RATIO = 0.75        # Max loan-to-value

# ─── App Settings ────────────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
