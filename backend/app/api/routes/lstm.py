from app.core.security import get_current_user
from app.db.session import get_db
from app.models.stock import Stock
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ml.dataset import DatasetBuilder
from ml.lstm import LSTMTrainer

router = APIRouter(prefix="/ml/lstm", tags=["lstm"])


@router.post("/train")
async def train_lstm_endpoint(
    symbol: str,
    epochs: int = 50,
    batch_size: int = 16,
    patience: int = 5,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Train LSTM on symbol's historical features.

    Returns: {
        "symbol": str,
        "model_version": str,
        "metrics": {...},
        "status": "trained"
    }
    """
    # Verify symbol exists
    stock = db.query(Stock).filter(Stock.symbol == symbol).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    try:
        # Build dataset (requires an active DB session)
        builder = DatasetBuilder(session=db)
        bundle = builder.build(symbol=symbol)

        if bundle is None or len(bundle.X_train) < 50:
            raise HTTPException(
                status_code=400, detail=f"Insufficient data for {symbol} (need >= 50 samples)"
            )

        # Train LSTM
        trainer = LSTMTrainer(device="cpu")  # Use CPU for Windows compatibility
        result = trainer.train_lstm(
            X_train=bundle.X_train,
            y_train=bundle.y_train,
            X_val=bundle.X_val,
            y_val=bundle.y_val,
            epochs=epochs,
            batch_size=batch_size,
            patience=patience,
            model_path=f"models/lstm_{symbol}_v1.pt",
        )

        return {
            "symbol": symbol,
            "model_version": "1.0",
            "metrics": result["metrics"],
            "status": "trained",
            "model_path": result["path"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
