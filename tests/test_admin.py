
from fastapi.testclient import TestClient

from models import User
from security import hash_password, create_access_token


def create_test_user(test_db, username, role):
    db = test_db()
    try:
        user = User(
            username=username,
            password=hash_password("test_password123"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def auth_headers(user_id):
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_normal_user_cannot_access_admin_articles(client, test_db):
    user_id = create_test_user(test_db, "normal_admin_test", "user")

    response = client.get(
        "/admin/articles",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 403


def test_admin_can_access_admin_articles(client, test_db):
    admin_id = create_test_user(test_db, "admin_test_user", "admin")

    response = client.get(
        "/admin/articles",
        headers=auth_headers(admin_id),
    )

    assert response.status_code == 200
