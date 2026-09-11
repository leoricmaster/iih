from fastapi.testclient import TestClient

from iih.web.app import create_app


def test_healthz_reports_database_up() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
