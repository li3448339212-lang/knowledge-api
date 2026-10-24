from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from datetime import datetime

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)

class UserUpdate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)

class PasswordUpdate(BaseModel):
    old_password: str = Field(..., min_length=6, max_length=72)
    new_password: str = Field(..., min_length=6, max_length=72)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)

class ArticleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    is_public: bool = False

class ArticleResponse(BaseModel):
    id: int
    title: str
    content: str
    username: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    view_count: int
    favorite_count: int
    is_favorited: bool
    is_liked: bool
    like_count: int
    comment_count: int
    

    model_config = ConfigDict(from_attributes=True)

class ArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    is_public: bool | None = None

class ArticleListResponse(BaseModel):
    items: list[ArticleResponse]
    page: int
    size: int
    total: int

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class RoleUpdate(BaseModel):
    role: UserRole

class ArticleViewResponse(BaseModel):
    user_id: int
    username: str

class ArticleLikeResponse(BaseModel):
    user_id: int
    username: str

class ArticleViewStatsResponse(BaseModel):
    article_id: int
    view_count: int
    unique_viewers: int

class APIResponse(BaseModel):
    code: int
    message: str
    data: object | None = None

class ArticleAPIResponse(BaseModel):
    code: int
    message: str
    data: ArticleResponse

class ArticleListAPIResponse(BaseModel):
    code: int
    message: str
    data: ArticleListResponse

class ArticleCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class ArticleCommentResponse(BaseModel):
    id: int
    article_id: int
    user_id: int
    username: str
    content: str
    created_at: datetime



class ArticleCommentCreateResponse(APIResponse):
    pass

class ArticleCommentListResponse(BaseModel):
    items: list[ArticleCommentResponse]
    page: int
    size: int
    total: int

class ArticleCommentListAPIResponse(BaseModel):
    code: int
    message: str
    data: ArticleCommentListResponse