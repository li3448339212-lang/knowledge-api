from fastapi.testclient import TestClient

from models import User, Article
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
            title="测试文章",
            content="文章权限测试内容",
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


def test_create_article_requires_authentication(
    client: TestClient,
):
    response = client.post(
        "/articles",
        json={
            "title": "未登录文章",
            "content": "未登录用户不应该创建文章",
        },
    )

    assert response.status_code == 401


def test_user_cannot_update_others_article(
    client: TestClient,
    test_db,
):
    owner_id = create_test_user(test_db, "article_owner")
    other_user_id = create_test_user(test_db, "article_other")
    article_id = create_test_article(test_db, owner_id)

    response = client.put(
        f"/articles/{article_id}",
        headers=auth_headers(other_user_id),
        json={
            "title": "被其他用户修改",
            "content": "不应该修改成功",
        },
    )

    assert response.status_code == 403

    db = test_db()
    try:
        article = db.query(Article).filter(
            Article.id == article_id
        ).first()

        assert article is not None
        assert article.title == "测试文章"
        assert article.content == "文章权限测试内容"
    finally:
        db.close()


def test_user_cannot_delete_others_article(
    client: TestClient,
    test_db,
):
    owner_id = create_test_user(test_db, "delete_owner")
    other_user_id = create_test_user(test_db, "delete_other")
    article_id = create_test_article(test_db, owner_id)

    response = client.delete(
        f"/articles/{article_id}",
        headers=auth_headers(other_user_id),
    )

    assert response.status_code == 403

    db = test_db()
    try:
        article = db.query(Article).filter(
            Article.id == article_id
        ).first()

        assert article is not None
        assert article.is_deleted is False
    finally:
        db.close()

def test_article_list_excludes_deleted_articles(
    client: TestClient,
    test_db,
):
    # 1. 创建用户
    user_id = create_test_user(
        test_db,
        "deleted_article_owner",
    )

    # 2. 创建一篇正常文章
    visible_article_id = create_test_article(
        test_db,
        user_id,
    )

    # 3. 创建一篇已软删除的文章
    db = test_db()
    try:
        deleted_article = Article(
            title="已删除文章",
            content="这篇文章不应该出现在列表中",
            user_id=user_id,
            is_deleted=True,
        )
        db.add(deleted_article)
        db.commit()
        db.refresh(deleted_article)
        deleted_article_id = deleted_article.id
    finally:
        db.close()

    # 4. 登录用户访问文章列表
    response = client.get(
        "/articles",
        headers=auth_headers(user_id),
    )

    assert response.status_code == 200

    # 5. 检查列表中不包含已删除文章
    body = response.json()
    items = body["data"]["items"]

    article_ids = [
        article["id"]
        for article in items
    ]

    assert visible_article_id in article_ids
    assert deleted_article_id not in article_ids


def test_article_list_keyword_search(
    client: TestClient,
    test_db,
):
    # 1. 创建测试用户
    user_id = create_test_user(
        test_db,
        "search_article_owner",
    )

    # 2. 创建两篇内容不同的文章
    db = test_db()
    try:
        article1 = Article(
            title="Python学习指南",
            content="学习FastAPI的基础知识",
            user_id=user_id,
            is_deleted=False,
        )

        article2 = Article(
            title="MySQL入门",
            content="学习数据库基础",
            user_id=user_id,
            is_deleted=False,
        )

        db.add_all([article1, article2])
        db.commit()
        db.refresh(article1)
        db.refresh(article2)

        article1_id = article1.id
        article2_id = article2.id
    finally:
        db.close()

    # 3. 搜索标题中包含 Python 的文章
    response = client.get(
        "/articles",
        params={"keyword": "Python"},
        headers=auth_headers(user_id),
    )

    # 4. 验证搜索结果
    assert response.status_code == 200

    body = response.json()
    items = body["data"]["items"]

    article_ids = [
        article["id"]
        for article in items
    ]

    assert article1_id in article_ids
    assert article2_id not in article_ids


def test_article_list_pagination(
    client: TestClient,
    test_db,
):
    # 1. 创建测试用户
    user_id = create_test_user(
        test_db,
        "pagination_owner",
    )

    # 2. 创建 3 篇文章
    db = test_db()
    try:
        articles = [
            Article(
                title=f"分页测试文章{i}",
                content=f"分页测试内容{i}",
                user_id=user_id,
                is_deleted=False,
            )
            for i in range(1, 4)
        ]

        db.add_all(articles)
        db.commit()

        for article in articles:
            db.refresh(article)

    finally:
        db.close()

    # 3. 查询第 1 页，每页 2 篇
    response1 = client.get(
        "/articles",
        params={"page": 1, "size": 2},
        headers=auth_headers(user_id),
    )

    # 4. 查询第 2 页，每页 2 篇
    response2 = client.get(
        "/articles",
        params={"page": 2, "size": 2},
        headers=auth_headers(user_id),
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    body1 = response1.json()["data"]
    body2 = response2.json()["data"]

    # 第 1 页有 2 篇，第 2 页有 1 篇
    assert len(body1["items"]) == 2
    assert len(body2["items"]) == 1

    # 总文章数为 3
    assert body1["total"] == 3
    assert body2["total"] == 3

    # 两页没有重复文章
    ids1 = {article["id"] for article in body1["items"]}
    ids2 = {article["id"] for article in body2["items"]}

    assert ids1.isdisjoint(ids2)
