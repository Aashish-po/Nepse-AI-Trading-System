"""WebSocket routes for streaming signal updates."""

from __future__ import annotations

import json
import logging

from app.services.signal_streamer import signal_stream_publisher
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["streaming"])


@router.websocket("/signals")
async def stream_signals(websocket: WebSocket) -> None:
    """Stream signal events to a subscribed client.

    The client should send a JSON message like:
    {"symbol": "NABIL"}
    """
    await websocket.accept()
    symbol = "ALL"
    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        symbol = str(payload.get("symbol", "ALL")).upper()
        await signal_stream_publisher.subscribe(symbol, websocket)
        await websocket.send_json({"status": "subscribed", "symbol": symbol})

        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                await websocket.send_json({"status": "error", "detail": "Invalid JSON"})
                continue

            if data.get("action") == "unsubscribe":
                await websocket.send_json({"status": "unsubscribed", "symbol": symbol})
                break
            if "symbol" in data and str(data["symbol"]).upper() != symbol:
                await signal_stream_publisher.unsubscribe(symbol, websocket)
                symbol = str(data["symbol"]).upper()
                await signal_stream_publisher.subscribe(symbol, websocket)
                await websocket.send_json({"status": "subscribed", "symbol": symbol})
    except WebSocketDisconnect:
        logger.debug("Signal websocket disconnected for %s", symbol)
    finally:
        await signal_stream_publisher.unsubscribe(symbol, websocket)
