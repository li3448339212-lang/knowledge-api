from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_protected_article_creation_requires_authentication():
    response = client.post(
        "/articles",
        json={
            "title": "自动化测试文章",
            "content": "这是一篇测试文章。",
        },
    )

    assert response.status_code == 401


def test_admin_article_list_requires_authentication():
    response = client.get("/admin/articles")

    assert response.status_code == 401