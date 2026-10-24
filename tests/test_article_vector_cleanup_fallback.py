
from unittest.mock import patch

from fastapi.testclient import TestClient

from models import User, Article, VectorCleanupTask
from security import hash_password, create_access_token


def create_test_user(test_db, username):
    db = test_db()
    try:
        user = User(
            username=username,
            password=hash_password("test_password123"),
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id
    finally:
        db.close()


def create_test_article(test_db, user_id):
    db = test_db()
    try:
        article = Article(
            title="向量清理补偿测试",
            content="测试文章删除后向量清理失败的情况",
            user_id=user_id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article.id
    finally:
        db.close()


def auth_headers(user_id):
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_delete_article_creates_cleanup_task_when_vector_delete_fails(
    client: TestClient,
    test_db,
):
    user_id = create_test_user(
        test_db,
        "vector_cleanup_fallback_user",
    )
    article_id = create_test_article(test_db, user_id)

    with patch(
        "routers.articles.vector_store.delete_by_article_id",
        side_effect=RuntimeError("模拟 ChromaDB 清理失败"),
    ):
        response = client.delete(
            f"/articles/{article_id}",
            headers=auth_headers(user_id),
        )

    assert response.status_code == 200

    db = test_db()
    try:
        task = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.article_id == article_id,
                VectorCleanupTask.status == "pending",
            )
            .first()
        )

        assert task is not None
        assert task.retry_count == 0
        assert "模拟 ChromaDB 清理失败" in task.last_error

    finally:
        db.close()
