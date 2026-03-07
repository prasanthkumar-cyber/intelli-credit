import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from typing import Dict, Any

class LoanRecommender:
    """ML Model for predicting optimal loan amounts based on historical proxy data."""
    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.is_trained = False
        self._train_dummy_model()

    def _train_dummy_model(self):
        """Train on dummy data representing our lending policy."""
        # Features: [Revenue, Collateral, Net Worth, EBITDA, Risk Score, Total Debt]
        # Target: Approved Loan Amount
        
        X = np.array([
            [10.0, 5.0, 6.0, 2.0, 20.0, 1.0],  # Excellent: Get max loan (~min(2xRev, .8xCol))
            [2.0,  1.0, 1.0, 0.4, 40.0, 0.5],  # Average
            [5.0,  2.0, 3.0, 1.0, 30.0, 1.0],  # Good
            [0.5,  0.0, 0.2, 0.05, 85., 0.8],  # Poor: get ~0
            [15.0, 8.0, 10.0, 3.0, 15.0, 2.0], # Outstanding
        ])
        
        y = np.array([4.0, 0.8, 1.6, 0.0, 6.4])
        
        self.model.fit(X, y)
        self.is_trained = True
        
    def predict(self, features: Dict[str, float]) -> float:
        """Predict the optimal loan amount (in Cr)"""
        if not self.is_trained:
            return 0.0
            
        x_in = np.array([[
            features.get("revenue", 0.0),
            features.get("collateral_value", 0.0),
            features.get("net_worth", 0.0),
            features.get("ebitda", 0.0),
            features.get("risk_score", 50.0),
            features.get("total_debt", 0.0)
        ]])
        
        pred = self.model.predict(x_in)[0]
        return max(round(pred, 2), 0)

# Global singleton
recommender = LoanRecommender()
