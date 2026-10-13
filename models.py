from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, DateTime, func, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

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