from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, insert
from exceptions import (
    NotFoundError,
    PermissionDeniedError,
    BadRequestError
)
from models import Article, ArticleFavorite, ArticleLike, ArticleView, ArticleComment, User
from redis_client import redis_client
import json
from datetime import datetime
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from rag.vector_store import vector_store
import logging
from rag.cleanup_tasks import create_cleanup_task

logger = logging.getLogger(__name__)

def build_article_data(
    article,
    is_favorited=False,
    is_liked=False
):
    return {
        "id": article.id,
        "title": article.title,
        "content": article.content,
        "user_id": article.user_id,
        "username": article.user.username if article.user else None,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
        "view_count": article.view_count,
        "favorite_count": article.favorite_count,
        "like_count": article.like_count,
        "comment_count": article.comment_count,
        "is_favorited": is_favorited,
        "is_liked": is_liked
    }

def get_articles_service(
    db: Session,
    page: int,
    size: int,
    keyword: str,
    sort: str,
    user_id: int
):
    query = db.query(Article).options(
        joinedload(Article.user)
    ).filter(
        Article.is_deleted == False
    )

    # 搜索标题或者内容
    if keyword:
        query = query.filter(
            or_(
                Article.title.like("%" + keyword + "%"),
                Article.content.like("%" + keyword + "%")
            )
        )

    # 统计符合条件的文章总数
    total = query.count()

    # 排序
    if sort == "views":
        query = query.order_by(Article.view_count.desc())
    elif sort == "asc":
        query = query.order_by(Article.created_at.asc())
    else:
        query = query.order_by(Article.created_at.desc())

    # 分页
    articles = query.offset(
        (page - 1) * size
    ).limit(size).all()

    article_ids = [article.id for article in articles]

    favorite_ids = {
        row.article_id
        for row in db.query(ArticleFavorite.article_id).filter(
            ArticleFavorite.article_id.in_(article_ids),
            ArticleFavorite.user_id == user_id
        ).all()
    }

    like_ids = {
        row.article_id
        for row in db.query(ArticleLike.article_id).filter(
            ArticleLike.article_id.in_(article_ids),
            ArticleLike.user_id == user_id
        ).all()
    }

    items = []

    for article in articles:
        is_favorited = article.id in favorite_ids
        is_liked = article.id in like_ids

        items.append(
            build_article_data(
                article,
                is_favorited=is_favorited,
                is_liked=is_liked
            )
        )


    return {
        "items": items,
        "page": page,
        "size": size,
        "total": total
    }


def create_article_service(
    db: Session,
    title: str,
    content: str,
    user_id: int,
    is_public: bool = False
):
    new_article = Article(
        title=title,
        content=content,
        user_id=user_id,
        is_public=is_public
    )

    try:
        db.add(new_article)
        db.commit()
        db.refresh(new_article)
    except Exception:
        db.rollback()
        raise

    return new_article


def update_article_service(
    db: Session,
    article_id: int,
    title: str,
    content: str,
    user_id: int,
    is_public: bool | None = None
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    if article.user_id != user_id:
        raise PermissionDeniedError()

    if title is not None:
        article.title = title

    if content is not None:
        article.content = content

    if is_public is not None:
        article.is_public = is_public

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(article)
    is_favorited = db.query(ArticleFavorite).filter(
        ArticleFavorite.article_id == article_id,
        ArticleFavorite.user_id == user_id
    ).first() is not None

    is_liked = db.query(ArticleLike).filter(
        ArticleLike.article_id == article_id,
        ArticleLike.user_id == user_id
    ).first() is not None

    try:
        redis_client.delete(
            f"article:{article_id}"
        )
    except Exception:
        pass

    return build_article_data(
        article,
        is_favorited=is_favorited,
        is_liked=is_liked
    )

def delete_article_service(
    db: Session,
    article_id: int,
    user_id: int
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    if article.user_id != user_id:
        raise PermissionDeniedError()

    article.is_deleted = True
    
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    try:
        redis_client.delete(
            f"article:{article_id}"
        )
    except Exception:
        pass

        # 尝试清理文章向量，最多重试 2 次
    vector_deleted = False
    last_error = None

    for attempt in range(2):
        try:
            vector_store.delete_by_article_id(article_id)
            vector_deleted = True
            break
        except Exception as e:
            last_error = str(e)

            logger.exception(
                "文章向量清理失败，第 %s 次尝试，article_id=%s",
                attempt + 1,
                article_id,
            )

    # 两次清理都失败，创建补偿任务，交给后台 worker 重试
    if not vector_deleted:
        try:
            create_cleanup_task(
                db=db,
                article_id=article_id,
                error_message=(
                    f"向量清理连续两次失败。"
                    f"最后一次错误：{last_error}"
                ),
            )
        except Exception:
            logger.exception(
                "保存向量清理任务失败，article_id=%s",
                article_id,
            )


    return article

def get_article_service(
    db: Session,
    article_id: int,
    user_id: int
):
    cache_key = f"article:{article_id}"

    # 1. 锁定文章记录，防止浏览处理期间文章被并发删除
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).with_for_update().first()

    if article is None:
        raise NotFoundError()

    # 2. 从 Redis 读取缓存
    try:
        cached_article = redis_client.get(cache_key)
    except Exception:
        cached_article = None

    article_data = None

    if cached_article:
        try:
            cached_data = json.loads(cached_article)

            # 验证缓存是否与数据库中的文章一致，
            # 避免缓存失效前的旧内容被返回
            if (
                isinstance(cached_data, dict)
                and cached_data.get("id") == article.id
                and cached_data.get("title") == article.title
                and cached_data.get("content") == article.content
                and cached_data.get("user_id") == article.user_id
                and cached_data.get("username")
                == (article.user.username if article.user else None)
                and cached_data.get("created_at")
                == article.created_at.isoformat()
                and cached_data.get("updated_at")
                == article.updated_at.isoformat()
            ):
                article_data = cached_data

        except (
            json.JSONDecodeError,
            TypeError,
            UnicodeDecodeError,
            AttributeError
        ):
            article_data = None

    # 3. 缓存不存在、损坏或内容过期时，使用数据库数据
    if article_data is None:
        article_data = {
            "id": article.id,
            "title": article.title,
            "content": article.content,
            "user_id": article.user_id,
            "username": article.user.username if article.user else None,
            "created_at": article.created_at.isoformat(),
            "updated_at": article.updated_at.isoformat()
        }

        try:
            redis_client.set(
                cache_key,
                json.dumps(article_data),
                ex=300
            )
        except Exception:
            # Redis 不可用时仍允许查询文章
            pass

    # 4. 原子地登记浏览记录
    # ArticleView 必须有 article_id、user_id 联合唯一约束
    
    try:
        dialect_name = db.get_bind().dialect.name

        if dialect_name == "sqlite":
            stmt = sqlite_insert(ArticleView).values(
                article_id=article_id,
                user_id=user_id,
            ).on_conflict_do_nothing(
                index_elements=["article_id", "user_id"]
            )
        else:
            stmt = mysql_insert(ArticleView).prefix_with("IGNORE").values(
                article_id=article_id,
                user_id=user_id,
            )

        result = db.execute(stmt)


        # 只有成功新增浏览记录，才增加浏览量
        if result.rowcount == 1:
            db.query(Article).filter(
                Article.id == article_id,
                Article.is_deleted == False
            ).update(
                {
                    Article.view_count:
                        Article.view_count + 1
                },
                synchronize_session=False
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    # 5. 查询当前用户的收藏状态
    is_favorited = db.query(
        ArticleFavorite.id
    ).filter(
        ArticleFavorite.article_id == article_id,
        ArticleFavorite.user_id == user_id
    ).first() is not None

    # 6. 查询当前用户的点赞状态
    is_liked = db.query(
        ArticleLike.id
    ).filter(
        ArticleLike.article_id == article_id,
        ArticleLike.user_id == user_id
    ).first() is not None

    # 7. 查询最新浏览量
    view_count = db.query(
        Article.view_count
    ).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).scalar()

    if view_count is None:
        raise NotFoundError()

    # 8. 查询收藏、点赞和评论数量
    favorite_count = db.query(
        ArticleFavorite.id
    ).filter(
        ArticleFavorite.article_id == article_id
    ).count()

    like_count = db.query(
        ArticleLike.id
    ).filter(
        ArticleLike.article_id == article_id
    ).count()

    comment_count = db.query(
        ArticleComment.id
    ).filter(
        ArticleComment.article_id == article_id
    ).count()

    # 9. 返回文章详情
    return {
        "id": article_data["id"],
        "title": article_data["title"],
        "content": article_data["content"],
        "user_id": article_data["user_id"],
        "username": article_data["username"],
        "created_at": datetime.fromisoformat(
            article_data["created_at"]
        ),
        "updated_at": datetime.fromisoformat(
            article_data["updated_at"]
        ),
        "view_count": view_count,
        "favorite_count": favorite_count,
        "like_count": like_count,
        "comment_count": comment_count,
        "is_favorited": is_favorited,
        "is_liked": is_liked
    }

def get_my_articles_service(
    db: Session,
    user_id: int,
    sort: str,
    page: int,
    size: int,
    keyword: str
):
    query = db.query(Article).options(
        joinedload(Article.user)
    ).filter(
        Article.user_id == user_id,
        Article.is_deleted == False
    )

    if keyword:
        query = query.filter(
            or_(
                Article.title.like("%" + keyword + "%"),
                Article.content.like("%" + keyword + "%")
            )
        )

    if sort == "asc":
        query = query.order_by(
            Article.created_at.asc()
        )
    elif sort == "views":
        query = query.order_by(
            Article.view_count.desc(),
            Article.created_at.desc()
        )
    else:
        query = query.order_by(
            Article.created_at.desc()
        )

    total = query.count()

    articles = query.offset(
        (page - 1) * size
    ).limit(size).all()

    article_ids = [article.id for article in articles]

    favorite_ids = {
        row.article_id
        for row in db.query(ArticleFavorite.article_id).filter(
            ArticleFavorite.article_id.in_(article_ids),
            ArticleFavorite.user_id == user_id
        ).all()
    }
    
    like_ids = {
        row.article_id
        for row in db.query(ArticleLike.article_id).filter(
            ArticleLike.article_id.in_(article_ids),
            ArticleLike.user_id == user_id
        ).all()
    }

    items = []

    for article in articles:
        is_favorited = article.id in favorite_ids
        is_liked = article.id in like_ids

        items.append(
            build_article_data(
                article,
                is_favorited=is_favorited,
                is_liked=is_liked
            )
        )

    return {
        "items": items,
        "page": page,
        "size": size,
        "total": total
    }

def get_all_articles_service(
    db: Session
):
    articles = db.query(Article).options(
        joinedload(Article.user)
    ).filter(
        Article.is_deleted == False
    ).all()

    items = []

    for article in articles:
        items.append(
            build_article_data(
                article
            )
        )

    return items

def admin_delete_article_service(
    db: Session,
    article_id: int
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    article.is_deleted = True

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        redis_client.delete(
            f"article:{article_id}"
        )
    except Exception:
        pass

    return article

def restore_article_service(
    db: Session,
    article_id: int
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == True
    ).first()

    if article is None:
        raise NotFoundError()

    article.is_deleted = False
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    try:
        redis_client.delete(
            f"article:{article_id}"
        )
    except Exception:
        pass

    return article

def get_article_views_service(
    db: Session,
    article_id: int,
    user_id: int,
    role: str
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    # 只有文章作者或管理员可以查看详细浏览记录
    if article.user_id != user_id and role != "admin":
        raise PermissionDeniedError()

    views = db.query(
        ArticleView.user_id,
        User.username
    ).join(
        User,
        ArticleView.user_id == User.id
    ).filter(
        ArticleView.article_id == article_id
    ).all()

    return [
        {
            "user_id": view.user_id,
            "username": view.username
        }
        for view in views
    ]

def get_article_view_stats_service(
    db: Session,
    article_id: int
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    unique_viewers = db.query(
        ArticleView.user_id
    ).filter(
        ArticleView.article_id == article_id
    ).distinct().count()

    return {
        "article_id": article.id,
        "view_count": article.view_count,
        "unique_viewers": unique_viewers
    }


def favorite_article_service(
    db: Session,
    article_id: int,
    user_id: int
):
    article = db.query(Article.id).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    try:
        # 检查用户是否已经收藏过这篇文章
        existing_favorite = db.query(ArticleFavorite).filter(
            ArticleFavorite.article_id == article_id,
            ArticleFavorite.user_id == user_id
        ).first()

        if existing_favorite is not None:
            raise BadRequestError("Article already favorited")

        # 创建收藏记录
        favorite = ArticleFavorite(
            article_id=article_id,
            user_id=user_id
        )
        db.add(favorite)
        db.commit()

    except BadRequestError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "article_id": article_id,
        "user_id": user_id,
        "is_favorited": True
    }


def unfavorite_article_service(
    db: Session,
    article_id: int,
    user_id: int
):
    # 先检查文章是否存在且未被删除
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    # 查找当前用户的收藏记录
    favorite = db.query(ArticleFavorite).filter(
        ArticleFavorite.article_id == article_id,
        ArticleFavorite.user_id == user_id
    ).first()

    if not favorite:
        raise NotFoundError()

    try:
        db.delete(favorite)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return favorite


def get_my_favorites_service(
    db: Session,
    user_id: int,
    page: int = 1,
    size: int = 10
):
    query = db.query(ArticleFavorite).join(
        Article,
        Article.id == ArticleFavorite.article_id
    ).filter(
        ArticleFavorite.user_id == user_id,
        Article.is_deleted == False
    )

    total = query.count()

    favorites = query.order_by(
        ArticleFavorite.id.desc()
    ).offset(
        (page - 1) * size
    ).limit(size).all()

    items = []

    for favorite in favorites:
        article = favorite.article

        is_liked = db.query(
            ArticleLike.id
        ).filter(
            ArticleLike.article_id == article.id,
            ArticleLike.user_id == user_id
        ).first() is not None

        items.append(
            build_article_data(
                article,
                is_favorited=True,
                is_liked=is_liked
            )
        )

    return {
        "items": items,
        "page": page,
        "size": size,
        "total": total
    }


def like_article_service(
    db: Session,
    article_id: int,
    user_id: int
):
    article = db.query(Article.id).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    try:
        # 检查用户是否已经点赞
        existing_like = db.query(ArticleLike).filter(
            ArticleLike.article_id == article_id,
            ArticleLike.user_id == user_id
        ).first()

        if existing_like is not None:
            raise BadRequestError("Article already liked")

        # 创建点赞记录
        like = ArticleLike(
            article_id=article_id,
            user_id=user_id
        )
        db.add(like)
        db.commit()

    except BadRequestError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "article_id": article_id,
        "user_id": user_id,
        "is_liked": True
    }


def get_article_likes_service(
    db: Session,
    article_id: int
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    likes = db.query(
        ArticleLike.user_id,
        User.username
    ).join(
        User,
        User.id == ArticleLike.user_id
    ).filter(
        ArticleLike.article_id == article_id
    ).all()

    return [
        {
            "user_id": user_id,
            "username": username
        }
        for user_id, username in likes
    ]


def unlike_article_service(
    db: Session,
    article_id: int,
    user_id: int
):
    # 检查文章是否存在且未被删除
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    # 查找当前用户的点赞记录
    like = db.query(ArticleLike).filter(
        ArticleLike.article_id == article_id,
        ArticleLike.user_id == user_id
    ).first()

    if like is None:
        raise NotFoundError()

    try:
        db.delete(like)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return like


def get_my_likes_service(
    db: Session,
    user_id: int,
    page: int = 1,
    size: int = 10
):
    query = db.query(ArticleLike).join(
        Article,
        Article.id == ArticleLike.article_id
    ).filter(
        ArticleLike.user_id == user_id,
        Article.is_deleted == False
    )

    total = query.count()

    likes = query.order_by(
        ArticleLike.id.desc()
    ).offset(
        (page - 1) * size
    ).limit(size).all()

    items = []

    for like in likes:
        article = like.article

        is_favorited = db.query(
            ArticleFavorite.id
        ).filter(
            ArticleFavorite.article_id == article.id,
            ArticleFavorite.user_id == user_id
        ).first() is not None

        items.append(
            build_article_data(
                article,
                is_favorited=is_favorited,
                is_liked=True
            )
        )

    return {
        "items": items,
        "page": page,
        "size": size,
        "total": total
    }

def create_comment_service(
    db: Session,
    article_id: int,
    user_id: int,
    content: str
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    comment = ArticleComment(
        article_id=article_id,
        user_id=user_id,
        content=content
    )

    try:
        db.add(comment)
        db.commit()
        db.refresh(comment)
    except Exception:
        db.rollback()
        raise

    user = db.query(User).filter(
        User.id == user_id
    ).first()

    return {
        "id": comment.id,
        "article_id": comment.article_id,
        "user_id": comment.user_id,
        "username": user.username,
        "content": comment.content,
        "created_at": comment.created_at
    }

def get_article_comments_service(
    db: Session,
    article_id: int,
    page: int,
    size: int
):
    article = db.query(Article).filter(
        Article.id == article_id,
        Article.is_deleted == False
    ).first()

    if article is None:
        raise NotFoundError()

    comments = db.query(
        ArticleComment,
        User.username
    ).join(
        User,
        User.id == ArticleComment.user_id
    ).filter(
        ArticleComment.article_id == article_id
    ).order_by(
        ArticleComment.created_at.asc()
    ).offset(
        (page - 1) * size
    ).limit(
        size
    ).all()

    total = db.query(ArticleComment).filter(
        ArticleComment.article_id == article_id
    ).count()

    items = [
        {
            "id": comment.id,
            "article_id": comment.article_id,
            "user_id": comment.user_id,
            "username": username,
            "content": comment.content,
            "created_at": comment.created_at
        }
        for comment, username in comments
    ]

    return {
        "items": items,
        "page": page,
        "size": size,
        "total": total
    }

def delete_comment_service(
    db: Session,
    comment_id: int,
    user_id: int
):
    comment = db.query(ArticleComment).filter(
        ArticleComment.id == comment_id
    ).first()

    if comment is None:
        raise NotFoundError()

    if comment.user_id != user_id:
        raise PermissionDeniedError()
    
    try:
        db.delete(comment)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return comment

def admin_delete_comment_service(
    db: Session,
    comment_id: int
):
    comment = db.query(ArticleComment).filter(
        ArticleComment.id == comment_id
    ).first()

    if comment is None:
        raise NotFoundError()

    try:
        db.delete(comment)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return comment