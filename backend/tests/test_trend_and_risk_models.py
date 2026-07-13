from __future__ import annotations

import numpy as np
import pandas as pd

from ml.risk_models import RiskModel
from ml.trend import TREND_REGIMES, TrendAnalyzer, build_trend_features, regime_from_returns


def test_trend_analyzer_fits_and_predicts_regime() -> None:
    up_leg = np.linspace(100.0, 140.0, 50)
    flat_leg = np.linspace(140.0, 141.0, 20)
    down_leg = np.linspace(141.0, 95.0, 50)
    prices = np.concatenate([up_leg, flat_leg, down_leg])
    frame = pd.DataFrame({"index_close": prices})

    features = build_trend_features(frame)
    regimes = regime_from_returns(pd.Series(prices).pct_change().fillna(0.0))

    analyzer = TrendAnalyzer(random_state=42, n_estimators=100)
    analyzer.fit(features, regimes)

    prediction = analyzer.predict_regime(features)
    probabilities = analyzer.predict_proba(features)

    assert prediction in TREND_REGIMES
    assert abs(sum(probabilities.values()) - 1.0) < 1e-6
    assert set(probabilities).issubset(set(TREND_REGIMES))


def test_risk_model_forecasts_tail_metrics() -> None:
    returns = np.array([0.01, 0.015, -0.005, 0.02, -0.012, 0.008, -0.01, 0.013, 0.006, -0.004])

    model = RiskModel(alpha=0.08, beta=0.9)
    model.fit(returns)
    forecast = model.forecast(horizon_days=1)
    assessment = model.to_risk_assessment(forecast)

    assert forecast.ewma_volatility > 0
    assert forecast.garch_volatility > 0
    assert forecast.var_99 <= forecast.var_95
    assert forecast.cvar_99 <= forecast.var_99
    assert assessment["status"] in {"normal", "elevated", "critical"}
    assert assessment["action"] in {"NORMAL", "REDUCE", "HOLD_ONLY"}
