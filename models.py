from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(20), default="user", nullable=False)

    articles = relationship(
        "Article",
        back_populates="user",
        cascade="all, delete-orphan"
    )

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    user = relationship("User", back_populates="articles")

    favorites = relationship(
        "ArticleFavorite",
        back_populates="article",
        cascade="all, delete-orphan"
    )

    likes = relationship(
        "ArticleLike",
        back_populates="article",
        cascade="all, delete-orphan"
    )

    comments = relationship(
        "ArticleComment",
        back_populates="article",
        cascade="all, delete-orphan"
    )

    is_public = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0"
    )

    @property
    def like_count(self):
        return len(self.likes)

    @property
    def favorite_count(self):
        return len(self.favorites)

    @property
    def comment_count(self):
        return len(self.comments)

    @property
    def username(self):
        return self.user.username


class ArticleView(Base):
    __tablename__ = "article_views"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "user_id",
            name="uq_article_view_user"
        ),
    )


class ArticleFavorite(Base):
    __tablename__ = "article_favorites"

    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "user_id",
            name="uq_article_favorite_user"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    article_id = Column(
        Integer,
        ForeignKey("articles.id"),
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    article = relationship(
        "Article",
        back_populates="favorites"
    )

class ArticleLike(Base):
    __tablename__ = "article_likes"

    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "user_id",
            name="uq_article_like_user"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    article_id = Column(
        Integer,
        ForeignKey("articles.id"),
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    article = relationship(
        "Article",
        back_populates="likes"
    )

class ArticleComment(Base):
    __tablename__ = "article_comments"

    id = Column(Integer, primary_key=True, index=True)

    article_id = Column(
        Integer,
        ForeignKey("articles.id"),
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    content = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    article = relationship(
        "Article",
        back_populates="comments"
    )

class VectorCleanupTask(Base):
    __tablename__ = "vector_cleanup_tasks"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, nullable=False, index=True)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def process_pending_cleanup_tasks(
    session_factory,
    max_retries: int = 5,
    batch_size: int = 20,
) -> int:
    """扫描待处理任务并自动重试，返回本轮处理的任务数量。"""
    from sqlalchemy import and_

    processed = 0
    db = session_factory()

    try:
        # 超过重试上限的任务标记为失败，避免无限重试
        exhausted_tasks = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.status == "pending",
                VectorCleanupTask.retry_count >= max_retries,
            )
            .limit(batch_size)
            .all()
        )

        for task in exhausted_tasks:
            task.status = "failed"

        db.commit()

        # 只取尚未达到重试上限的任务
        task_ids = [
            task_id
            for (task_id,) in (
                db.query(VectorCleanupTask.id)
                .filter(
                    VectorCleanupTask.status == "pending",
                    VectorCleanupTask.retry_count < max_retries,
                )
                .order_by(VectorCleanupTask.id.asc())
                .limit(batch_size)
                .all()
            )
        ]
    except Exception:
        db.rollback()
        logger.exception("扫描向量清理任务失败")
        return 0
    finally:
        db.close()

    # 每个任务使用独立数据库会话，避免任务失败互相影响
    for task_id in task_ids:
        task_db = session_factory()
        try:
            retry_cleanup_task(task_db, task_id)
            processed += 1
        except Exception:
            logger.exception("处理向量清理任务时发生异常，task_id=%s", task_id)
        finally:
            task_db.close()

    return processed
