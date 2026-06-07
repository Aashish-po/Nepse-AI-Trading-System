"""Machine learning research and model lifecycle modules."""

from backend.ml.dataset import DatasetBuilder, DatasetBundle, WalkForwardWindow
from backend.ml.drift_monitoring import (
    CorrelationMonitor,
    DriftMonitor,
    DriftResult,
    TrustScoreMonitor,
)
from backend.ml.evaluation import ModelEvaluator
from backend.ml.experiment_tracking import ExperimentRecord, ExperimentTracker
from backend.ml.feature_vector import (
    FEATURE_DIM,
    FEATURE_ORDER,
    build_feature_vector,
    fill_missing,
    validate_vector,
)
from backend.ml.inference import Predictor
from backend.ml.labeling import LabelConfig, LabelMode, create_labels
from backend.ml.position_sizing import PositionSize, PositionSizer, SizingMethod
from backend.ml.predictions import MLModelAdapter, ModelAdapter, Prediction
from backend.ml.risk_management import RiskDecision, RiskManager, RiskState, StopLossManager
from backend.ml.training import ModelTrainer, TrainingResult

__all__ = [
    "DatasetBuilder",
    "DatasetBundle",
    "WalkForwardWindow",
    "DriftMonitor",
    "CorrelationMonitor",
    "TrustScoreMonitor",
    "DriftResult",
    "ModelEvaluator",
    "ExperimentTracker",
    "ExperimentRecord",
    "FEATURE_ORDER",
    "FEATURE_DIM",
    "build_feature_vector",
    "fill_missing",
    "validate_vector",
    "Predictor",
    "create_labels",
    "LabelConfig",
    "LabelMode",
    "PositionSizer",
    "PositionSize",
    "SizingMethod",
    "ModelAdapter",
    "MLModelAdapter",
    "Prediction",
    "ModelTrainer",
    "TrainingResult",
    "RiskManager",
    "RiskState",
    "RiskDecision",
    "StopLossManager",
]
