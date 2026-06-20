# Models

Trained model artifacts (`.joblib`, `.pt`, `.h5` files) are stored here.

## Structure

```
models/
├── baseline/         # Logistic, RF, XGBoost models
├── lstm/             # LSTM forecasting models
├── sentiment/        # Sentiment analysis models
├── experimental/     # PPO, DQN, GNN models
└── README.md
```

## Model Registry

Models are tracked in the database with:

- Model ID and version
- Training metadata
- Performance metrics
- Governance state (development → staging → production)

## File Formats

- **Baseline/LSTM**: `.joblib` (scikit-learn, XGBoost)
- **PyTorch**: `.pt` (LSTM, PPO, DQN)
- **Sentiment**: `.joblib` or `.bin` (XLM-R)
- **GNN**: `.h5` or `.pt`

## Note

This directory is gitignored. Model artifacts should not be committed to version control. Use the model registry API for model management.
