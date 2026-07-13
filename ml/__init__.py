"""Machine learning research and model lifecycle modules."""

from ml.dataset import DatasetBuilder, DatasetBundle, WalkForwardWindow
from ml.feature_vector import (
    FEATURE_DIM,
    FEATURE_ORDER,
    build_feature_vector,
    fill_missing,
    validate_vector,
)
from ml.inference import Predictor
from ml.labeling import LabelConfig, LabelMode, create_labels
from ml.risk_models import RiskForecast, RiskModel
from ml.training import ModelTrainer, TrainingResult
from ml.trend import TREND_REGIMES, TrendAnalyzer, TrendFeatureSet, build_trend_features

__all__ = [
    "DatasetBuilder",
    "DatasetBundle",
    "WalkForwardWindow",
    "FEATURE_ORDER",
    "FEATURE_DIM",
    "build_feature_vector",
    "fill_missing",
    "validate_vector",
    "Predictor",
    "create_labels",
    "LabelConfig",
    "LabelMode",
    "TREND_REGIMES",
    "TrendAnalyzer",
    "TrendFeatureSet",
    "build_trend_features",
    "RiskForecast",
    "RiskModel",
    "ModelTrainer",
    "TrainingResult",
]
