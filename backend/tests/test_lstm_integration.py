import pytest

from backend.app.db.session import SessionLocal
from ml.dataset import DatasetBuilder


def test_lstm_dataset_build_nabil():
    """LSTM dataset builder works for real NEPSE data"""
    db = SessionLocal()

    try:
        builder = DatasetBuilder(session=db)
        bundle = builder.build(symbol="NABIL")

        # Verify bundle structure
        assert bundle is not None, "Bundle should not be None"
        assert bundle.X_train is not None
        assert bundle.X_val is not None
        assert bundle.y_train is not None
        assert bundle.y_val is not None

        # Verify shapes
        assert len(bundle.X_train) > 0, "Training data should not be empty"
        assert len(bundle.X_val) > 0, "Validation data should not be empty"
        assert bundle.X_train.shape[1] > 0, "X_train should have features"
    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
