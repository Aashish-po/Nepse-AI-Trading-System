# Test for signal fusion engine
import pytest

from ml.signal_fusion import SignalFusionEngine


def test_signal_fusion():
    """Signal fusion combines multiple providers"""
    engine = SignalFusionEngine()

    signals = {
        "technical": {"signal": "BUY", "confidence": 0.85},
        "lstm": {"signal": "BUY", "confidence": 0.70},
        "sentiment": {"signal": "HOLD", "confidence": 0.60},
    }

    result = engine.fuse_signals(signals)

    assert result["signal"] in ["BUY", "SELL", "HOLD"]
    assert 0 <= result["confidence"] <= 1
    assert result["provider"] == "fusion"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
