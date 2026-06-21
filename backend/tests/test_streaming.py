from __future__ import annotations

import pytest
from app.services.signal_streamer import SignalEvent, SignalStreamPublisher


class _DummyWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload):
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_signal_stream_publisher_publish_and_snapshot():
    publisher = SignalStreamPublisher()
    ws = _DummyWebSocket()

    await publisher.subscribe("NABIL", ws)
    delivered = await publisher.publish(SignalEvent(symbol="NABIL", signal="BUY", confidence=0.87))

    assert delivered == 1
    assert ws.messages[0]["symbol"] == "NABIL"
    assert ws.messages[0]["signal"] == "BUY"

    snapshot = await publisher.snapshot()
    assert snapshot["NABIL"] == 1


def test_demo_broadcast_endpoint_delivers_to_websocket(client):
    with client.websocket_connect("/ws/signals") as websocket:
        websocket.send_json({"symbol": "NABIL"})
        ack = websocket.receive_json()
        assert ack["status"] == "subscribed"

        response = client.post(
            "/signals/demo-broadcast",
            params={"symbol": "NABIL", "signal": "BUY", "confidence": 0.9},
        )
        assert response.status_code == 200
        assert response.json()["delivered"] >= 1

        payload = websocket.receive_json()
        assert payload["symbol"] == "NABIL"
        assert payload["signal"] == "BUY"
        assert payload["confidence"] == 0.9
