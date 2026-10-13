from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_root_returns_hello_world():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_openapi_is_available():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "paths" in response.json()