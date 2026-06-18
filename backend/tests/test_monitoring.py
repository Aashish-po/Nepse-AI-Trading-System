"""Tests for Phase 14: monitoring, observability, and health probes."""

from __future__ import annotations

from app.services.monitoring import MetricsRegistry


class TestMetricsRegistry:
    def test_counter_increment(self) -> None:
        reg = MetricsRegistry()
        reg.inc_counter("http_requests_total", labels={"method": "GET"})
        reg.inc_counter("http_requests_total", labels={"method": "GET"})
        reg.inc_counter("http_requests_total", labels={"method": "POST"})
        output = reg.render()
        assert 'http_requests_total{method="GET"} 2.0' in output
        assert 'http_requests_total{method="POST"} 1.0' in output

    def test_histogram_observation(self) -> None:
        reg = MetricsRegistry()
        for v in (0.001, 0.02, 0.3, 5.0):
            reg.observe("http_request_duration_seconds", v)
        output = reg.render()
        assert "http_request_duration_seconds_bucket" in output
        assert "http_request_duration_seconds_count" in output
        assert "http_request_duration_seconds_sum" in output
        # 4 observations total.
        assert "_count " in output

    def test_histogram_cumulative_buckets(self) -> None:
        reg = MetricsRegistry()
        reg.observe("lat", 0.001)  # falls in first bucket
        reg.observe("lat", 10.0)  # falls in last bucket
        output = reg.render()
        # +Inf bucket must equal total count (2).
        assert 'lat_bucket{le="+Inf"} 2' in output

    def test_reset(self) -> None:
        reg = MetricsRegistry()
        reg.inc_counter("c")
        reg.reset()
        assert reg.render().strip() == ""

    def test_type_headers(self) -> None:
        reg = MetricsRegistry()
        reg.inc_counter("my_counter")
        reg.observe("my_hist", 0.5)
        output = reg.render()
        assert "# TYPE my_counter counter" in output
        assert "# TYPE my_hist histogram" in output


class TestHealthProbes:
    def test_liveness(self, client) -> None:
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_readiness_ok(self, client) -> None:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"

    def test_health_basic(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestMetricsEndpoint:
    def test_metrics_endpoint_exposed(self, client) -> None:
        # Make a request so the middleware records something.
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "http_requests_total" in resp.text

    def test_metrics_records_requests(self, client) -> None:
        client.get("/health/live")
        resp = client.get("/metrics")
        assert "http_request_duration_seconds" in resp.text
