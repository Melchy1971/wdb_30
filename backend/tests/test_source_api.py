from fastapi.testclient import TestClient
from uuid import uuid4

from app.api.deps import get_session
from app.main import create_app


def test_create_and_validate_source_via_api(session, workspace_tmp_path):
    file_path = workspace_tmp_path / "document.txt"
    file_path.write_text("hello", encoding="utf-8")
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_session] = lambda: session
    source_id = f"api-valid-{uuid4()}"

    with TestClient(app) as client:
        create_response = client.post(
            "/sources",
            json={
                "source_id": source_id,
                "display_name": "API Valid",
                "source_system": "local",
                "location_uri": str(file_path),
                "is_active": True,
            },
        )
        validate_response = client.post(f"/sources/{source_id}/validate")

    assert create_response.status_code == 201
    assert validate_response.status_code == 200
    assert validate_response.json()["validation_status"] == "valid"


def test_get_unknown_source_returns_standard_error_code(session):
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_session] = lambda: session

    with TestClient(app) as client:
        response = client.get("/sources/unknown-source")

    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


def test_create_duplicate_source_returns_standard_error_code(session, workspace_tmp_path):
    file_path = workspace_tmp_path / "document.txt"
    file_path.write_text("hello", encoding="utf-8")
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_session] = lambda: session
    source_id = f"api-duplicate-{uuid4()}"
    payload = {
        "source_id": source_id,
        "display_name": "API Duplicate",
        "source_system": "local",
        "location_uri": str(file_path),
        "is_active": True,
    }

    with TestClient(app) as client:
        first = client.post("/sources", json=payload)
        second = client.post("/sources", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error_code"] == "CONFLICT"
