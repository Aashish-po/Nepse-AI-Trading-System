# ML

Machine learning modules for training, inference, and model management.

## Structure

```
ml/
├── dataset.py           # Walk-forward dataset builder
├── feature_vector.py    # Feature vector assembly/validation
├── labeling.py          # Label generation for supervised training
├── training.py          # Walk-forward training pipeline
├── inference.py         # Model prediction wrapper
├── lstm.py              # LSTM next-day forecasting
├── sentiment.py         # XLM-R and lexicon sentiment analysis
├── explainability.py    # SHAP-based model interpretability
├── meta_learning.py     # Meta-learning research (experimental)
├── model_io.py          # Model serialization/deserialization
└── risk_manager.py      # ML risk management
```

## Models

- **Baseline models**: Logistic regression, Random Forest, XGBoost
- **LSTM**: Time-series forecasting for price direction
- **Sentiment**: XLM-R multilingual or lexicon-based sentiment
- **Meta-learning (experimental)**: research module under `meta_learning.py`

> RL (PPO/DQN) and GNN modules are planned but not yet implemented.

## Training Pipeline

```python
from ml.training import train_baseline_model

# Walk-forward training with cross-validation
model = train_baseline_model(symbol="NABIL", model_type="xgboost")
```

## Inference

```python
from ml.inference import predict_signal

# Get model prediction
signal = predict_signal(symbol="NABIL", features=features_dict)
```

## Experimental Modules

The meta-learning module (`meta_learning.py`) is research-only. PPO, DQN, and GNN modules are planned for Phase 14 but not yet implemented.
