"""Machine learning research and model lifecycle modules."""

from ml.dataset import DatasetBuilder, DatasetBundle, WalkForwardWindow
from ml.drift_monitoring import CorrelationMonitor, DriftMonitor, DriftResult, TrustScoreMonitor
from ml.evaluation import ModelEvaluator
from ml.experiment_tracking import ExperimentRecord, ExperimentTracker
from ml.feature_vector import (
    FEATURE_DIM,
    FEATURE_ORDER,
    build_feature_vector,
    fill_missing,
    validate_vector,
)
from ml.inference import Predictor
from ml.labeling import LabelConfig, LabelMode, create_labels
from ml.position_sizing import PositionSize, PositionSizer, SizingMethod
from ml.predictions import MLModelAdapter, ModelAdapter, Prediction
from ml.risk_management import RiskDecision, RiskManager, RiskState, StopLossManager
from ml.training import ModelTrainer, TrainingResult

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
