"""
Intelli-Credit — Main Entry Point
Run with: python main.py
"""
import uvicorn

if __name__ == "__main__":
    print("[Intelli-Credit] Starting server...")
    print("[INFO] Training XGBoost model if not already trained...")

    # Pre-train models
    from engine.training_data import train_models
    import os, config
    if not os.path.exists(config.CLASSIFIER_PATH):
        train_models()
    else:
        print("[OK] Models already trained.")

    # Initialize Databricks tables
    try:
        from databricks_client import DatabricksClient
        db = DatabricksClient()
        db.initialize_schema()
    except Exception as e:
        print(f"[WARN] Databricks init: {e}")

    print("\n[START] Server starting at http://localhost:8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
