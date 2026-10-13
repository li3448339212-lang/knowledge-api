
from fastapi.testclient import TestClient

from models import User, Article, ArticleLike, ArticleFavorite, ArticleComment
from security import hash_password, create_access_token


def create_user(test_db, username):
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


def create_article(test_db, user_id):
    db = test_db()
    try:
        article = Article(
            title="互动测试文章",
            content="用于测试评论、点赞和收藏",
            user_id=user_id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article.id
    finally:
        db.close()


def headers_for(user_id):
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def test_like_article(client: TestClient, test_db):
    user_id = create_user(test_db, "like_test_user")
    article_id = create_article(test_db, user_id)

    response = client.post(
        f"/articles/{article_id}/like",
        headers=headers_for(user_id),
    )

    assert response.status_code == 200

    db = test_db()
    try:
        like = db.query(ArticleLike).filter_by(
            article_id=article_id,
            user_id=user_id,
        ).first()
        assert like is not None
    finally:
        db.close()


def test_unlike_article(client: TestClient, test_db):
    user_id = create_user(test_db, "unlike_test_user")
    article_id = create_article(test_db, user_id)

    like_response = client.post(
        f"/articles/{article_id}/like",
        headers=headers_for(user_id),
    )
    assert like_response.status_code == 200

    response = client.delete(
        f"/articles/{article_id}/like",
        headers=headers_for(user_id),
    )

    assert response.status_code == 200

    db = test_db()
    try:
        like = db.query(ArticleLike).filter_by(
            article_id=article_id,
            user_id=user_id,
        ).first()
        assert like is None
    finally:
        db.close()


def test_favorite_article(client: TestClient, test_db):
    user_id = create_user(test_db, "favorite_test_user")
    article_id = create_article(test_db, user_id)

    response = client.post(
        f"/articles/{article_id}/favorite",
        headers=headers_for(user_id),
    )

    assert response.status_code == 200

    db = test_db()
    try:
        favorite = db.query(ArticleFavorite).filter_by(
            article_id=article_id,
            user_id=user_id,
        ).first()
        assert favorite is not None
    finally:
        db.close()


def test_unfavorite_article(client: TestClient, test_db):
    user_id = create_user(test_db, "unfavorite_test_user")
    article_id = create_article(test_db, user_id)

    favorite_response = client.post(
        f"/articles/{article_id}/favorite",
        headers=headers_for(user_id),
    )
    assert favorite_response.status_code == 200

    response = client.delete(
        f"/articles/{article_id}/favorite",
        headers=headers_for(user_id),
    )

    assert response.status_code == 200

    db = test_db()
    try:
        favorite = db.query(ArticleFavorite).filter_by(
            article_id=article_id,
            user_id=user_id,
        ).first()
        assert favorite is None
    finally:
        db.close()


def test_create_comment(client: TestClient, test_db):
    user_id = create_user(test_db, "comment_test_user")
    article_id = create_article(test_db, user_id)

    response = client.post(
        f"/articles/{article_id}/comments",
        headers=headers_for(user_id),
        json={"content": "这是一条测试评论"},
    )

    assert response.status_code == 200

    db = test_db()
    try:
        comment = db.query(ArticleComment).filter_by(
            article_id=article_id,
            user_id=user_id,
        ).first()
        assert comment is not None
        assert comment.content == "这是一条测试评论"
    finally:
        db.close()


def test_user_cannot_delete_another_users_comment(
    client: TestClient,
    test_db,
):
    owner_id = create_user(test_db, "comment_owner_user")
    other_id = create_user(test_db, "comment_other_user")
    article_id = create_article(test_db, owner_id)

    comment_response = client.post(
        f"/articles/{article_id}/comments",
        headers=headers_for(owner_id),
        json={"content": "只有作者可以删除这条评论"},
    )
    assert comment_response.status_code == 200

    db = test_db()
    try:
        comment = db.query(ArticleComment).filter_by(
            article_id=article_id,
            user_id=owner_id,
        ).first()
        assert comment is not None
        comment_id = comment.id
    finally:
        db.close()

    response = client.delete(
        f"/articles/comments/{comment_id}",
        headers=headers_for(other_id),
    )

    assert response.status_code == 403

    db = test_db()
    try:
        comment = db.query(ArticleComment).filter_by(
            id=comment_id,
        ).first()
        assert comment is not None
    finally:
        db.close()