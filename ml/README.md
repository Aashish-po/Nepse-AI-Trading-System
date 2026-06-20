# ML

Machine learning modules for training, inference, and model management.

## Structure

```
ml/
├── training.py          # Walk-forward training pipeline
├── inference.py         # Model prediction wrapper
├── lstm.py              # LSTM next-day forecasting
├── sentiment.py         # XLM-R and lexicon sentiment analysis
├── signal_fusion.py     # ML signal combination
├── explainability.py    # SHAP-based model interpretability
├── ensemble.py          # Model ensemble implementation
├── ppo.py             # PPO reinforcement learning (experimental)
├── dqn.py             # DQN reinforcement learning (experimental)
├── gnn.py             # Graph neural network (experimental)
├── meta_learning.py     # Meta-learning research (experimental)
├── model_io.py          # Model serialization/deserialization
├── experiment_tracking.py # MLflow integration
├── drift_monitoring.py  # Data drift detection
└── risk_manager.py      # ML risk management
```

## Models

- **Baseline models**: Logistic regression, Random Forest, XGBoost
- **LSTM**: Time-series forecasting for price direction
- **Sentiment**: XLM-R multilingual or lexicon-based sentiment
- **RL (experimental)**: PPO and DQN for strategy optimization
- **GNN (experimental)**: Graph-based feature relationships

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

PPO, DQN, GNN, and meta-learning modules are for research purposes only. See Phase 14 documentation for details.
