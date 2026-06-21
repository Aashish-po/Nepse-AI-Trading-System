"""In-memory real-time signal streaming helper.

The service keeps subscriptions in-process and fans out JSON-compatible payloads
to connected WebSocket clients. It is intentionally lightweight so tests can
exercise the streaming behavior without external infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    symbol: str
    signal: str
    confidence: float
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class SignalStreamPublisher:
    """Publish signal events to subscribed WebSocket clients."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, symbol: str, websocket) -> None:
        symbol = symbol.upper()
        async with self._lock:
            self._subscribers[symbol].add(websocket)
        logger.debug("Subscribed websocket to %s", symbol)

    async def unsubscribe(self, symbol: str, websocket) -> None:
        symbol = symbol.upper()
        async with self._lock:
            sockets = self._subscribers.get(symbol)
            if sockets and websocket in sockets:
                sockets.remove(websocket)
                if not sockets:
                    self._subscribers.pop(symbol, None)
        logger.debug("Unsubscribed websocket from %s", symbol)

    async def publish(self, event: SignalEvent) -> int:
        payload = {
            "symbol": event.symbol.upper(),
            "signal": event.signal.upper(),
            "confidence": float(event.confidence),
            "timestamp": event.timestamp,
            "metadata": event.metadata,
        }

        async with self._lock:
            targets = list(self._subscribers.get(event.symbol.upper(), set()))

        delivered = 0
        for websocket in targets:
            try:
                await websocket.send_json(payload)
                delivered += 1
            except Exception:
                logger.exception("Failed to send signal event to websocket")
        return delivered

    async def publish_signal(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Convenience wrapper for publishing a signal snapshot."""
        return await self.publish(
            SignalEvent(
                symbol=symbol.upper(),
                signal=signal.upper(),
                confidence=confidence,
                metadata=metadata or {},
            )
        )

    async def snapshot(self) -> dict[str, int]:
        async with self._lock:
            return {symbol: len(clients) for symbol, clients in self._subscribers.items()}


signal_stream_publisher = SignalStreamPublisher()
