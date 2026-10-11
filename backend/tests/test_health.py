import logging
import time

from fastapi.testclient import TestClient

from app.main import create_app


class Probe:
    def postgres(self):
        pass

    def cache(self):
        pass


def test_live_and_ready(settings):
    with TestClient(create_app(settings, Probe())) as client:
        assert client.get("/health/live").json()["status"] == "ok"
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["checks"] == {"postgres": "ok", "redis": "ok"}
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"


def test_dependency_failure_is_503_without_secrets(settings):
    class Broken(Probe):
        def postgres(self):
            raise RuntimeError("postgresql://user:secret@private-db")

    with TestClient(create_app(settings, Broken())) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "secret" not in response.text
        assert response.json()["checks"]["redis"] == "ok"
        assert client.get("/health/live").status_code == 200


def test_slow_dependency_is_bounded(settings):
    class Slow(Probe):
        def cache(self):
            time.sleep(0.3)

    settings.readiness_timeout_seconds = 0.1
    with TestClient(create_app(settings, Slow())) as client:
        started = time.monotonic()
        assert client.get("/health/ready").status_code == 503
        assert time.monotonic() - started < 0.25


def test_host_and_cors(settings):
    with TestClient(create_app(settings, Probe())) as client:
        assert client.get("/health/live", headers={"Host": "evil.example"}).status_code == 400
        bad = client.get("/health/live", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in bad.headers
        good = client.get("/health/live", headers={"Origin": settings.public_origin})
        assert good.headers["access-control-allow-origin"] == settings.public_origin


def test_logs_exclude_query_and_authorization(settings, caplog):
    with caplog.at_level(logging.INFO, logger="suni.requests"):
        with TestClient(create_app(settings, Probe())) as client:
            client.get("/health/live?token=secret-query", headers={"Authorization": "secret-auth"})
    records = [r.message for r in caplog.records if r.name == "suni.requests"]
    assert records
    assert all("secret-query" not in r and "secret-auth" not in r for r in records)


def test_production_hides_docs(settings):
    settings.app_env = "production"
    settings.public_origin = "https://cinema.example.com"
    with TestClient(create_app(settings, Probe())) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert "strict-transport-security" in client.get("/health/live").headers
