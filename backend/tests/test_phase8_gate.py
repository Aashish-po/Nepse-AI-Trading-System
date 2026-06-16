import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.session import SessionLocal
from app.models.feature import Features
from app.models.price import Price
from app.models.stock import Stock

from backend.app.services.signal_fusion import SignalFusionEngine
from ml.dataset import DatasetBuilder
from ml.lstm import LSTMTrainer


@pytest.fixture
def db_with_data():
    """Fixture: DB with synthetic NABIL price & feature data"""
    db = SessionLocal()

    # Get or create stock
    stock = db.query(Stock).filter(Stock.symbol == "NABIL").first()
    if not stock:
        stock = Stock(symbol="NABIL", name="Nabil Bank", sector="Finance", is_active=True)
        db.add(stock)
        db.commit()
        db.refresh(stock)

    stock_id = stock.id

    # Create 100 days of price data
    base_date = datetime(2024, 1, 1)
    base_price = 1200.0

    for i in range(100):
        date = base_date + timedelta(days=i)
        price_val = base_price + (i * 0.5)

        existing = (
            db.query(Price)
            .filter((Price.stock_id == stock_id) & (Price.date == date.date()))
            .first()
        )
        if existing:
            continue

        price = Price(
            stock_id=stock_id,
            date=date.date(),
            open=price_val - 5,
            high=price_val + 10,
            low=price_val - 10,
            close=price_val,
            volume=100000,
        )
        db.add(price)

    db.commit()

    # Create 100 days of feature data
    for i in range(100):
        date = base_date + timedelta(days=i)

        existing = (
            db.query(Features)
            .filter((Features.stock_id == stock_id) & (Features.date == date.date()))
            .first()
        )
        if existing:
            continue

        feature = Features(
            stock_id=stock_id,
            date=date.date(),
            feature_version="v4.0.0",
            confidence=0.85 + (i * 0.001),
            features_meta={"rsi": 50 + i * 0.1, "sma20": 1200 + i * 0.5},
            values={"rsi": 50 + i * 0.1, "sma20": 1200 + i * 0.5},
        )
        db.add(feature)

    db.commit()
    yield db
    db.close()


class TestPhase8Gate:
    """Phase 8 gate criteria: LSTM + signal fusion working"""

    def test_lstm_training_completes(self, db_with_data):
        """LSTM training completes without errors"""
        try:
            builder = DatasetBuilder(session=db_with_data)
            bundle = builder.build(symbol="NABIL")

            assert bundle is not None
            assert len(bundle["X_train"]) > 20

            trainer = LSTMTrainer(device="cpu")
            result = trainer.train_lstm(
                X_train=bundle["X_train"],
                y_train=bundle["y_train"],
                X_val=bundle["X_val"],
                y_val=bundle["y_val"],
                epochs=5,
                batch_size=8,
                patience=3,
                model_path="models/test_lstm.pt",
            )

            assert result is not None
            assert "metrics" in result
            print(f"✅ LSTM complete: {result['metrics']}")
        except Exception as e:
            pytest.fail(f"LSTM failed: {str(e)}")

    def test_signal_fusion_3way(self, db_with_data):
        """Signal fusion: 3-provider consensus"""
        engine = SignalFusionEngine(db_with_data)
        signals = {
            "technical": {"signal": "BUY", "confidence": 0.90},
            "lstm": {"signal": "BUY", "confidence": 0.85},
            "sentiment": {"signal": "BUY", "confidence": 0.80},
        }
        result = engine.fuse_signals(signals)
        assert result["signal"] == "BUY"
        assert result["confidence"] > 0.7

    def test_signal_fusion_conflicting(self, db_with_data):
        """Signal fusion: conflicting signals"""
        engine = SignalFusionEngine(db_with_data)
        signals = {
            "technical": {"signal": "BUY", "confidence": 0.90},
            "lstm": {"signal": "SELL", "confidence": 0.85},
            "sentiment": {"signal": "HOLD", "confidence": 0.80},
        }
        result = engine.fuse_signals(signals)
        assert result["signal"] in ["BUY", "SELL", "HOLD"]
        assert 0 <= result["confidence"] <= 1

    def test_signal_fusion_missing_provider(self, db_with_data):
        """Signal fusion: partial signals"""
        engine = SignalFusionEngine(db_with_data)
        signals = {"technical": {"signal": "BUY", "confidence": 0.90}}
        result = engine.fuse_signals(signals)
        assert result["signal"] in ["BUY", "SELL", "HOLD"]
        assert 0 <= result["confidence"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
