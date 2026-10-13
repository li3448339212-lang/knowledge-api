from fastapi.testclient import TestClient

from models import User
from security import hash_password


def create_test_user(
    test_db,
    username="login_user",
    password="correct_password123",
):
    db = test_db()

    try:
        user = User(
            username=username,
            password=hash_password(password),
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


def test_login_success(client: TestClient, test_db):
    create_test_user(test_db)

    response = client.post(
        "/login",
        json={
            "username": "login_user",
            "password": "correct_password123",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient, test_db):
    create_test_user(test_db)

    response = client.post(
        "/login",
        json={
            "username": "login_user",
            "password": "wrong_password123",
        },
    )

    assert response.status_code == 401


def test_login_nonexistent_user(client: TestClient):
    response = client.post(
        "/login",
        json={
            "username": "no_such_user",
            "password": "correct_password123",
        },
    )

    assert response.status_code == 401