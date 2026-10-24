from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from rag.data_loader import text_splitter
from rag.vector_store import vector_store
from database import get_db
from models import Article, VectorCleanupTask
from schemas import (
    ArticleCreate,
    ArticleUpdate,
    ArticleCommentCreate,
    APIResponse,
    ArticleListAPIResponse,
    ArticleCommentListAPIResponse,
    ArticleAPIResponse
)

from security import get_current_user, get_admin_user
from logger import logger

from services.article_service import (
    get_articles_service,
    create_article_service,
    update_article_service,
    delete_article_service,
    get_article_service,
    get_my_articles_service,
    get_all_articles_service,
    admin_delete_article_service,
    restore_article_service,
    get_article_views_service,
    get_article_view_stats_service,
    favorite_article_service,
    unfavorite_article_service,
    get_my_favorites_service,
    like_article_service,
    get_article_likes_service,
    unlike_article_service,
    get_my_likes_service,
    create_comment_service,
    get_article_comments_service,
    delete_comment_service,
    build_article_data,
    admin_delete_comment_service
)  

router = APIRouter()


@router.post(
    "/articles/{article_id}/favorite",
    response_model=APIResponse
)
def favorite_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    favorite_article_service(
        db,
        article_id,
        current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "Article favorited successfully",
        "data": None
    }


@router.post(
    "/articles/{article_id}/like",
    response_model=APIResponse
)
def like_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    like_article_service(
        db,
        article_id,
        current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "Article liked successfully",
        "data": None
    }

@router.post(
    "/articles/{article_id}/comments",
    response_model=APIResponse
)
def create_comment(
    article_id: int,
    comment_data: ArticleCommentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    comment = create_comment_service(
        db,
        article_id,
        current_user["user_id"],
        comment_data.content
    )

    return {
        "code": 200,
        "message": "Comment created successfully",
        "data": comment
    }

@router.get(
    "/articles/{article_id}/comments",
    response_model=ArticleCommentListAPIResponse
)
def get_article_comments(
    article_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    comments = get_article_comments_service(
        db,
        article_id,
        page,
        size
    )

    return {
        "code": 200,
        "message": "success",
        "data": comments
    }

@router.delete(
    "/articles/comments/{comment_id}",
    response_model=APIResponse
)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    delete_comment_service(
        db,
        comment_id,
        current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "Comment deleted successfully",
        "data": None
    }

@router.delete(
    "/admin/comments/{comment_id}",
    response_model=APIResponse
)
def admin_delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user)
):
    admin_delete_comment_service(
        db,
        comment_id
    )

    return {
        "code": 200,
        "message": "Comment deleted successfully",
        "data": None
    }

@router.delete(
    "/articles/{article_id}/favorite",
    response_model=APIResponse
)
def unfavorite_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    unfavorite_article_service(
        db,
        article_id,
        current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "Article unfavorited successfully",
        "data": None
    }

@router.delete(
    "/articles/{article_id}/like",
    response_model=APIResponse
)
def unlike_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    unlike_article_service(
        db,
        article_id,
        current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "Article unliked successfully",
        "data": None
    }

# 创建文章
@router.post("/articles", response_model=ArticleAPIResponse)
def create_article(
    article: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        new_article = create_article_service(
            db=db,
            title=article.title,
            content=article.content,
            user_id=current_user["user_id"],
            is_public=article.is_public
        )
    except Exception as e:
        logger.error(f"创建文章失败: {e}")
        raise

    # 【新增代码】：文章写入数据库成功后，自动同步到 RAG 知识库
    try:
        full_text = f"{new_article.title}\n{new_article.content}"
        chunks = text_splitter.split_text(full_text)
        if chunks:
            vector_store.update_article(
                chunks,
                article_id=new_article.id,
                user_id=new_article.user_id,
                is_public=new_article.is_public
            )
            logger.info(f"✅ 新文章 [{new_article.title}] 已自动同步到 RAG 知识库！")
    except Exception as e:
        # 即使 RAG 同步失败，也不影响文章的正常创建和返回
        logger.warning(f"⚠️ 文章已创建，但同步到 RAG 失败: {e}")

    logger.info(
        f"用户创建文章: user_id={current_user['user_id']}, "
        f"article_id={new_article.id}"
    )

    return {
        "code": 200,
        "message": "Article created successfully",
        "data": build_article_data(
            new_article
        )
    }

@router.get(
    "/articles/{article_id}/views",
    response_model=APIResponse
)
def get_article_views(
    article_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    views = get_article_views_service(
        db,
        article_id,
        current_user["user_id"],
        current_user["role"]
    )

    return {
        "code": 200,
        "message": "success",
        "data": views
    }

@router.get(
    "/articles/{article_id}/likes",
    response_model=APIResponse
)
def get_article_likes(
    article_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    likes = get_article_likes_service(
        db,
        article_id
    )

    return {
        "code": 200,
        "message": "success",
        "data": likes
    }


# 查询文章列表 + 分页 + 搜索
@router.get(
    "/articles",
    response_model=ArticleListAPIResponse
)
def get_articles(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    sort: str = Query("desc", pattern="^(asc|desc|views)$"),
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    articles = get_articles_service(
        db=db,
        page=page,
        size=size,
        keyword=keyword,
        sort=sort,
        user_id=current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "success",
        "data": articles
    }


# 查询单篇文章
@router.get("/articles/{article_id}", response_model=ArticleAPIResponse)
def get_article(
    article_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    article = get_article_service(
        db=db,
        article_id=article_id,
        user_id=current_user["user_id"]
    )

    return {
        "code": 200,
        "message": "success",
        "data": article
    }


# 修改文章
@router.put("/articles/{article_id}", response_model=ArticleAPIResponse)
def update_article(
    article_id: int,
    article_data: ArticleUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    article = update_article_service(
        db=db,
        article_id=article_id,
        title=article_data.title,
        content=article_data.content,
        user_id=current_user["user_id"],
        is_public=article_data.is_public
    )

    # 【修复】：将 updated_article 改为 article，与上面的返回值变量名保持一致
    try:
        full_text = f"{article['title']}\n{article['content']}"
        chunks = text_splitter.split_text(full_text)

        vector_store.update_article(
            chunks,
            article_id=article["id"],
            user_id=article["user_id"],
            is_public=article_data.is_public
            if article_data.is_public is not None
            else db.query(Article).filter(
                Article.id == article_id
            ).first().is_public
        )

        logger.info(
            f"✅ 文章 [ID: {article['id']}] 已同步更新到 RAG 知识库。"
        )
    except Exception as e:
        logger.warning(f"⚠️ 文章已更新，但同步 RAG 失败: {e}")

    logger.info(
        f"用户修改文章: user_id={current_user['user_id']}, "
        f"article_id={article['id']}"
    )

    return {
        "code": 200,
        "message": "Article updated successfully",
        "data": article
    }


# 删除文章

@router.delete("/articles/{article_id}", response_model=APIResponse)
def delete_article(
    article_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 1. 调用服务层删除文章
    delete_article_service(
        db=db,
        article_id=article_id,
        user_id=current_user["user_id"],
    )

    # 2. 记录用户操作
    logger.info(
        "用户删除文章：user_id=%s, article_id=%s",
        current_user["user_id"],
        article_id,
    )

    # 3. 返回响应
    return {
        "code": 200,
        "message": "Article deleted successfully",
        "data": None,
    }


@router.get("/my_articles", response_model=ArticleListAPIResponse)
def get_my_articles(
    sort: str = Query("desc", pattern="^(asc|desc|views)$"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    articles = get_my_articles_service(
        db=db,
        user_id=current_user["user_id"],
        page=page,
        size=size,
        sort=sort,
        keyword=keyword
    )

    return {
        "code": 200,
        "message": "success",
        "data": articles
    }

@router.get(
    "/admin/articles",
    response_model=ArticleListAPIResponse
)
def get_all_articles(
    db=Depends(get_db),
    current_user=Depends(get_admin_user)
):
    articles = get_all_articles_service(db)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": articles,
            "page": 1,
            "size": len(articles),
            "total": len(articles)
        }
    }

@router.delete(
    "/admin/articles/{article_id}",
    response_model=APIResponse
)
def admin_delete_article(
    article_id: int,
    db=Depends(get_db),
    current_user=Depends(get_admin_user)
):
    admin_delete_article_service(
        db,
        article_id
    )

    return {
        "code": 200,
        "message": "Article deleted successfully",
        "data": None
    }




@router.post(
    "/admin/articles/{article_id}/restore",
    response_model=APIResponse
)
def restore_article(
    article_id: int,
    db=Depends(get_db),
    current_user=Depends(get_admin_user)
):
    article = restore_article_service(
        db,
        article_id
    )

    try:
        from rag.text_splitter import text_splitter

        chunks = text_splitter.split_text(article.content)

        vector_store.update_article(
            chunks,
            article_id=article.id,
            user_id=article.user_id,
            is_public=article.is_public
        )

        logger.info(
            f"文章 [ID: {article.id}] 已重新同步到 RAG 知识库。"
        )
    except Exception as e:
        logger.warning(
            f"文章已恢复，但同步 RAG 失败: {e}"
        )

    return {
        "code": 200,
        "message": "Article restored successfully",
        "data": None
    }




@router.get(
    "/my_favorites",
    response_model=ArticleListAPIResponse
)
def get_my_favorites(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    data = get_my_favorites_service(
        db=db,
        user_id=current_user["user_id"],
        page=page,
        size=size
    )

    return {
        "code": 200,
        "message": "Favorites retrieved successfully",
        "data": data
    }


@router.get(
    "/my_likes",
    response_model=ArticleListAPIResponse
)
def get_my_likes(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    data = get_my_likes_service(
        db=db,
        user_id=current_user["user_id"],
        page=page,
        size=size
    )

    return {
        "code": 200,
        "message": "Likes retrieved successfully",
        "data": data
    }