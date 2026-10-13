from database import get_db
from redis_client import redis_client
from models import (
    User,
    Article,
    ArticleView,
    ArticleFavorite,
    ArticleLike,
    ArticleComment
)
from schemas import (
    UserResponse,
    UserCreate,
    UserUpdate,
    PasswordUpdate,
    LoginRequest,
    APIResponse,
    RoleUpdate
)
from fastapi import APIRouter, Depends
from security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_admin_user
)
from logger import logger
from exceptions import (
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    UnauthorizedError
)

router = APIRouter()


def delete_user_data(db, user):
    user_id = user.id

    # 找出该用户拥有的全部文章 ID，包括已软删除的文章
    article_ids = [
        row.id
        for row in db.query(Article.id).filter(
            Article.user_id == user_id
        ).all()
    ]

    try:
        # 删除该用户的浏览记录
        db.query(ArticleView).filter(
            ArticleView.user_id == user_id
        ).delete(synchronize_session=False)

        # 删除其文章的所有浏览记录
        if article_ids:
            db.query(ArticleView).filter(
                ArticleView.article_id.in_(article_ids)
            ).delete(synchronize_session=False)

        # 删除该用户的收藏记录
        db.query(ArticleFavorite).filter(
            ArticleFavorite.user_id == user_id
        ).delete(synchronize_session=False)

        # 删除其他用户对其文章的收藏记录
        if article_ids:
            db.query(ArticleFavorite).filter(
                ArticleFavorite.article_id.in_(article_ids)
            ).delete(synchronize_session=False)

        # 删除该用户的点赞记录
        db.query(ArticleLike).filter(
            ArticleLike.user_id == user_id
        ).delete(synchronize_session=False)

        # 删除其他用户对其文章的点赞记录
        if article_ids:
            db.query(ArticleLike).filter(
                ArticleLike.article_id.in_(article_ids)
            ).delete(synchronize_session=False)

        # 删除该用户发表的评论
        db.query(ArticleComment).filter(
            ArticleComment.user_id == user_id
        ).delete(synchronize_session=False)

        # 删除其文章下的所有评论
        if article_ids:
            db.query(ArticleComment).filter(
                ArticleComment.article_id.in_(article_ids)
            ).delete(synchronize_session=False)

        # 删除用户及其文章
        db.delete(user)
        db.commit()

    except Exception:
        db.rollback()
        raise

    # 数据库提交成功后，再清理文章缓存
    for article_id in article_ids:
        try:
            redis_client.delete(f"article:{article_id}")
        except Exception:
            # Redis 暂时不可用时，不影响已完成的数据库删除
            pass

# 查询所有用户
@router.get("/users", response_model=APIResponse)
def get_users(
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    users = db.query(User).all()

    return {
        "code": 200,
        "message": "success",
        "data": [
            UserResponse.model_validate(user)
            for user in users
        ]
    }


# 注册用户
@router.post("/users", response_model=APIResponse)
def create_user(
    user: UserCreate,
    db=Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.username == user.username
    ).first()

    if existing_user is not None:
        raise BadRequestError("Username already exists")

    new_user = User(
        username=user.username,
        password=hash_password(user.password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "code": 200,
        "message": "User created successfully",
        "data": UserResponse.model_validate(new_user)
    }


# 查询单个用户
@router.get("/users/{user_id}", response_model=APIResponse)
def get_user(
    user_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise NotFoundError()

    return {
        "code": 200,
        "message": "success",
        "data": UserResponse.model_validate(user)
    }

# 删除用户
@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise NotFoundError()

    if user.id != current_user["user_id"]:
        raise PermissionDeniedError()

    delete_user_data(db, user)

    return {
        "message": "User deleted successfully"
    }


# 修改用户名
@router.put("/users/{user_id}", response_model=APIResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise NotFoundError()

    if user.id != current_user["user_id"]:
        raise PermissionDeniedError()

    existing_user = db.query(User).filter(
        User.username == user_data.username,
        User.id != user_id
    ).first()

    if existing_user is not None:
        raise BadRequestError("Username already exists")

    user.username = user_data.username

    db.commit()
    db.refresh(user)

    return{
        "code": 200,
        "message": "User updated successfully",
        "data": UserResponse.model_validate(user)
    }

@router.delete("/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db=Depends(get_db),
    current_user=Depends(get_admin_user)
):
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise NotFoundError()

    if user.id == current_user["user_id"]:
        raise BadRequestError("不能删除自己的账号")

    delete_user_data(db, user)

    return {
        "message": "User deleted successfully"
    }



# 修改密码
@router.put("/users/{user_id}/password")
def update_password(
    user_id: int,
    user_data: PasswordUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise NotFoundError()

    if user.id != current_user["user_id"]:
        raise PermissionDeniedError()

    if not verify_password(
        user_data.old_password,
        user.password
    ):
        raise BadRequestError("旧密码错误")

    user.password = hash_password(
        user_data.new_password
    )

    db.commit()

    return {
        "message": "Password updated successfully"
    }


# 登录

@router.post("/login")
def login(
    login_data: LoginRequest,
    db=Depends(get_db)
):
    user = db.query(User).filter(
        User.username == login_data.username
    ).first()

    if user is None:
        logger.warning("用户登录失败：用户名或密码错误")
        raise UnauthorizedError("用户名或密码错误")

    if not verify_password(
        login_data.password,
        user.password
    ):
        logger.warning("用户登录失败：用户名或密码错误")
        raise UnauthorizedError("用户名或密码错误")

    token = create_access_token({
        "user_id": user.id
    })

    logger.info("用户登录成功")

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.put("/admin/users/{user_id}/role")
def update_user_role(
    user_id: int,
    role_data: RoleUpdate,
    db=Depends(get_db),
    current_user=Depends(get_admin_user)
):
    user = db.query(User).filter(
        User.id == user_id
    ).first()

    if user is None:
        raise NotFoundError()

    user.role = role_data.role

    db.commit()
    db.refresh(user)

    return{
        "code": 200,
        "message": "User updated successfully",
        "data": UserResponse.model_validate(user)
    }