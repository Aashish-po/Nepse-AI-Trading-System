from __future__ import annotations

from datetime import date

import numpy as np
from app.services.factor_analysis import FactorAnalysisService
from app.services.macro_data import MacroDataService, MacroSnapshot
from app.services.news_sentiment import NewsSentimentService


def test_factor_analysis_shapes():
    service = FactorAnalysisService()
    returns = np.array([[0.01, 0.02, 0.03], [0.02, 0.01, 0.04], [0.00, -0.01, 0.02]])

    result = service.compute_factors(returns, n_factors=2)

    assert result.factors.shape[1] == 2
    assert result.loadings.shape == (3, 2)
    assert len(result.explained_variance) == 2


def test_factor_attribution():
    service = FactorAnalysisService()
    exposures = {"AAA": [0.5, 0.2], "BBB": [0.1, 0.9]}

    attribution = service.factor_attribution(exposures, [0.04, -0.02])

    assert "AAA" in attribution
    assert attribution["BBB"] != attribution["AAA"]


def test_news_sentiment_scoring_and_adjustment():
    service = NewsSentimentService()

    positive = service.score_headline("Company posts record profit and strong growth")
    negative = service.score_headline("Company suffers loss and downgrade")

    assert positive > negative
    assert service.adjust_confidence(0.8, positive) > service.adjust_confidence(0.8, negative)


def test_macro_regime_detection():
    service = MacroDataService()
    service.add_snapshot(MacroSnapshot(as_of=date.today(), usd_npr=150.0))

    assert service.detect_regime() == "stress"
