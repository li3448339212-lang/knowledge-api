
from models import Article
from services.article_service import create_article_service


def test_create_article_service(test_db):
    # 1. 创建测试用户
    from models import User
    from security import hash_password

    db = test_db()
    try:
        user = User(
            username="service_create_user",
            password=hash_password("test_password123"),
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        user_id = user.id
    finally:
        db.close()

    # 2. 调用服务层创建文章
    db = test_db()
    try:
        article = create_article_service(
            db=db,
            title="服务层测试文章",
            content="这是服务层创建的文章",
            user_id=user_id,
        )

        # 3. 验证返回结果
        assert article.id is not None
        assert article.title == "服务层测试文章"
        assert article.content == "这是服务层创建的文章"
        assert article.user_id == user_id

        # 4. 验证文章确实保存到了数据库
        saved_article = (
            db.query(Article)
            .filter(Article.id == article.id)
            .first()
        )

        assert saved_article is not None
        assert saved_article.title == "服务层测试文章"

    finally:
        db.close()



import pytest
from exceptions import PermissionDeniedError
from services.article_service import update_article_service


def test_update_article_service_denies_other_user(test_db):
    # 1. 创建文章作者和另一名用户
    from models import User

    db = test_db()
    try:
        owner = User(
            username="service_update_owner",
            password="test_password123",
            role="user",
        )
        other_user = User(
            username="service_update_other",
            password="test_password123",
            role="user",
        )

        db.add_all([owner, other_user])
        db.commit()
        db.refresh(owner)
        db.refresh(other_user)

        owner_id = owner.id
        other_user_id = other_user.id

        # 2. 创建作者自己的文章
        article = Article(
            title="原始标题",
            content="原始内容",
            user_id=owner_id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id
    finally:
        db.close()

    # 3. 另一名用户尝试修改文章
    db = test_db()
    try:
        with pytest.raises(PermissionDeniedError):
            update_article_service(
                db=db,
                article_id=article_id,
                title="被修改的标题",
                content="被修改的内容",
                user_id=other_user_id,
            )

        # 4. 确认原文章没有被修改
        saved_article = (
            db.query(Article)
            .filter(Article.id == article_id)
            .first()
        )

        assert saved_article.title == "原始标题"
        assert saved_article.content == "原始内容"

    finally:
        db.close()


from exceptions import NotFoundError


def test_update_article_service_article_not_found(test_db):
    db = test_db()
    try:
        # 使用一个不存在的文章 ID
        with pytest.raises(NotFoundError):
            update_article_service(
                db=db,
                article_id=999999999,
                title="新标题",
                content="新内容",
                user_id=1,
            )
    finally:
        db.close()



def test_update_article_service_success(test_db):
    from models import User

    # 1. 创建作者和文章
    db = test_db()
    try:
        user = User(
            username="service_update_success",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="修改前标题",
            content="修改前内容",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        user_id = user.id
        article_id = article.id
    finally:
        db.close()

    # 2. 调用服务层修改文章
    db = test_db()
    try:
        updated_article = update_article_service(
            db=db,
            article_id=article_id,
            title="修改后标题",
            content="修改后内容",
            user_id=user_id,
        )

        # 3. 验证返回结果
        assert updated_article["title"] == "修改后标题"
        assert updated_article["content"] == "修改后内容"

        # 4. 验证数据库中的内容也已更新
        saved_article = (
            db.query(Article)
            .filter(Article.id == article_id)
            .first()
        )
        assert saved_article.title == "修改后标题"
        assert saved_article.content == "修改后内容"
    finally:
        db.close()



from services.article_service import delete_article_service


def test_delete_article_service_success(test_db):
    from models import User

    # 1. 创建用户和文章
    db = test_db()
    try:
        user = User(
            username="service_delete_owner",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="准备删除的文章",
            content="这篇文章将被软删除",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        user_id = user.id
        article_id = article.id
    finally:
        db.close()

    # 2. 作者删除自己的文章
    db = test_db()
    try:
        delete_article_service(
            db=db,
            article_id=article_id,
            user_id=user_id,
        )

        # 3. 验证文章仍在数据库中，但已被软删除
        deleted_article = (
            db.query(Article)
            .filter(Article.id == article_id)
            .first()
        )

        assert deleted_article is not None
        assert deleted_article.is_deleted is True
    finally:
        db.close()


def test_delete_article_service_creates_cleanup_task_on_vector_failure(
    test_db,
    monkeypatch,
):
    from models import User, Article, VectorCleanupTask
    import services.article_service as article_service

    # 模拟向量清理连续两次失败
    def fail_vector_cleanup(article_id):
        raise RuntimeError("模拟向量清理失败")

    monkeypatch.setattr(
        article_service.vector_store,
        "delete_by_article_id",
        fail_vector_cleanup,
    )

    db = test_db()
    try:
        user = User(
            username="cleanup_failure_test_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="向量清理失败测试文章",
            content="用于测试补偿任务创建",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id
        user_id = user.id

        delete_article_service(
            db=db,
            article_id=article_id,
            user_id=user_id,
        )

        task = (
            db.query(VectorCleanupTask)
            .filter(VectorCleanupTask.article_id == article_id)
            .order_by(VectorCleanupTask.id.desc())
            .first()
        )

        assert task is not None
        assert task.status == "pending"
        assert task.retry_count == 0
        assert "向量清理连续两次失败" in task.last_error

        saved_article = (
            db.query(Article)
            .filter(Article.id == article_id)
            .first()
        )
        assert saved_article is not None
        assert saved_article.is_deleted is True

    finally:
        db.close()



def test_delete_article_service_denies_other_user(test_db):
    from models import User
    from exceptions import PermissionDeniedError

    # 1. 创建文章作者和另一名用户
    db = test_db()
    try:
        owner = User(
            username="service_delete_owner2",
            password="test_password123",
            role="user",
        )
        other_user = User(
            username="service_delete_other",
            password="test_password123",
            role="user",
        )

        db.add_all([owner, other_user])
        db.commit()
        db.refresh(owner)
        db.refresh(other_user)

        owner_id = owner.id
        other_user_id = other_user.id

        # 2. 创建作者的文章
        article = Article(
            title="不能被别人删除",
            content="只有作者可以删除",
            user_id=owner_id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id
    finally:
        db.close()

    # 3. 另一名用户尝试删除
    db = test_db()
    try:
        with pytest.raises(PermissionDeniedError):
            delete_article_service(
                db=db,
                article_id=article_id,
                user_id=other_user_id,
            )

        # 4. 确认文章没有被删除
        saved_article = (
            db.query(Article)
            .filter(Article.id == article_id)
            .first()
        )

        assert saved_article is not None
        assert saved_article.is_deleted is False
    finally:
        db.close()


from services.article_service import get_article_service
from exceptions import NotFoundError


def test_get_article_service_success(test_db):
    from models import User

    # 1. 创建用户和文章
    db = test_db()
    try:
        user = User(
            username="service_detail_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="详情测试文章",
            content="这是文章详情的测试内容",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        user_id = user.id
        article_id = article.id
    finally:
        db.close()

    # 2. 调用文章详情服务
    db = test_db()
    try:
        result = get_article_service(
            db=db,
            article_id=article_id,
            user_id=user_id,
        )

        # 3. 检查返回结果
        assert result["id"] == article_id
        assert result["title"] == "详情测试文章"
        assert result["content"] == "这是文章详情的测试内容"
        assert result["user_id"] == user_id
    finally:
        db.close()


def test_article_view_count_only_increments_once_per_user(test_db):
    from models import User

    # 1. 创建两个用户和一篇文章
    db = test_db()
    try:
        user1 = User(
            username="view_count_user1",
            password="test_password123",
            role="user",
        )
        user2 = User(
            username="view_count_user2",
            password="test_password123",
            role="user",
        )
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        article = Article(
            title="浏览量测试文章",
            content="测试重复浏览",
            user_id=user1.id,
            is_deleted=False,
            is_public=True,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        user1_id = user1.id
        user2_id = user2.id
        article_id = article.id
    finally:
        db.close()

    # 2. 用户 1 第一次查看
    db = test_db()
    try:
        get_article_service(db, article_id, user1_id)
        db.refresh(
            db.query(Article)
            .filter(Article.id == article_id)
            .first()
        )
        article = db.query(Article).filter(
            Article.id == article_id
        ).first()
        assert article.view_count == 1
    finally:
        db.close()

    # 3. 用户 1 再次查看，浏览量不应增加
    db = test_db()
    try:
        get_article_service(db, article_id, user1_id)
        article = db.query(Article).filter(
            Article.id == article_id
        ).first()
        assert article.view_count == 1
    finally:
        db.close()

    # 4. 用户 2 查看，浏览量应增加
    db = test_db()
    try:
        get_article_service(db, article_id, user2_id)
        article = db.query(Article).filter(
            Article.id == article_id
        ).first()
        assert article.view_count == 2
    finally:
        db.close()


def test_get_article_service_not_found(test_db):
    db = test_db()
    try:
        with pytest.raises(NotFoundError):
            get_article_service(
                db=db,
                article_id=999999999,
                user_id=1,
            )
    finally:
        db.close()


def test_get_article_service_redis_get_error(test_db, monkeypatch):
    from models import User
    import services.article_service as article_service

    db = test_db()
    try:
        user = User(
            username="redis_error_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="Redis异常测试",
            content="测试缓存读取失败",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        article_id = article.id
        user_id = user.id
    finally:
        db.close()

    def raise_redis_error(*args, **kwargs):
        raise RuntimeError("Redis connection failed")

    monkeypatch.setattr(
        article_service.redis_client,
        "get",
        raise_redis_error,
    )

    db = test_db()
    try:
        result = get_article_service(db, article_id, user_id)
        assert result is not None
    finally:
        db.close()


def test_get_article_service_redis_set_error(test_db, monkeypatch):
    from models import User
    import services.article_service as article_service

    db = test_db()
    try:
        user = User(
            username="redis_set_error_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="Redis写入异常测试",
            content="测试缓存写入失败",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        article_id = article.id
        user_id = user.id
    finally:
        db.close()

    def raise_redis_set_error(*args, **kwargs):
        raise RuntimeError("Redis write failed")

    monkeypatch.setattr(
        article_service.redis_client,
        "get",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        article_service.redis_client,
        "set",
        raise_redis_set_error,
    )

    db = test_db()
    try:
        result = get_article_service(db, article_id, user_id)
        assert result is not None
    finally:
        db.close()




def test_update_article_service_not_found(test_db):
    db = test_db()
    try:
        with pytest.raises(NotFoundError):
            update_article_service(
                db=db,
                article_id=999999999,
                title="不存在的文章",
                content="这篇文章不存在",
                user_id=1,
            )
    finally:
        db.close()


def test_delete_article_service_not_found(test_db):
    db = test_db()
    try:
        with pytest.raises(NotFoundError):
            delete_article_service(
                db=db,
                article_id=999999999,
                user_id=1,
            )
    finally:
        db.close()


def test_delete_article_service_permission_denied(test_db):
    from models import User

    db = test_db()
    try:
        user1 = User(
            username="delete_owner",
            password="test_password123",
            role="user",
        )
        user2 = User(
            username="delete_other",
            password="test_password123",
            role="user",
        )
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        article = Article(
            title="权限测试文章",
            content="只有作者可以删除",
            user_id=user1.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id
        other_user_id = user2.id

        with pytest.raises(PermissionDeniedError):
            delete_article_service(
                db=db,
                article_id=article_id,
                user_id=other_user_id,
            )

        # 确认文章没有被删除
        db.refresh(article)
        assert article.is_deleted is False
    finally:
        db.close()


def test_update_article_service_permission_denied(test_db):
    from models import User

    db = test_db()
    try:
        owner = User(
            username="update_owner",
            password="test_password123",
            role="user",
        )
        other_user = User(
            username="update_other",
            password="test_password123",
            role="user",
        )
        db.add_all([owner, other_user])
        db.commit()
        db.refresh(owner)
        db.refresh(other_user)

        article = Article(
            title="原始标题",
            content="原始内容",
            user_id=owner.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id
        other_user_id = other_user.id

        with pytest.raises(PermissionDeniedError):
            update_article_service(
                db=db,
                article_id=article_id,
                title="被非法修改的标题",
                content="被非法修改的内容",
                user_id=other_user_id,
            )

        db.refresh(article)
        assert article.title == "原始标题"
        assert article.content == "原始内容"
    finally:
        db.close()

def test_create_article_service_rollback(test_db, monkeypatch):
    from services.article_service import create_article_service

    db = test_db()
    rollback_called = False

    def mock_commit():
        raise RuntimeError("模拟数据库提交失败")

    def mock_rollback():
        nonlocal rollback_called
        rollback_called = True

    monkeypatch.setattr(db, "commit", mock_commit)
    monkeypatch.setattr(db, "rollback", mock_rollback)

    try:
        with pytest.raises(RuntimeError, match="模拟数据库提交失败"):
            create_article_service(
                db=db,
                title="测试文章",
                content="测试内容",
                user_id=1,
            )

        assert rollback_called is True
    finally:
        db.close()

def test_create_article_service_success(test_db):
    from services.article_service import create_article_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="create_test_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = create_article_service(
            db=db,
            title="测试文章标题",
            content="这是测试文章的内容",
            user_id=user.id,
        )

        assert article.id is not None
        assert article.title == "测试文章标题"
        assert article.content == "这是测试文章的内容"
        assert article.user_id == user.id

        saved_article = db.query(Article).filter(
            Article.id == article.id
        ).first()

        assert saved_article is not None
    finally:
        db.close()

def test_delete_article_service_rollback(test_db, monkeypatch):
    from services.article_service import delete_article_service
    from models import User

    db = test_db()
    rollback_called = False

    try:
        user = User(
            username="delete_rollback_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="待删除文章",
            content="测试回滚",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id

        def mock_commit():
            raise RuntimeError("模拟数据库提交失败")

        def mock_rollback():
            nonlocal rollback_called
            rollback_called = True

        monkeypatch.setattr(db, "commit", mock_commit)
        monkeypatch.setattr(db, "rollback", mock_rollback)

        with pytest.raises(RuntimeError, match="模拟数据库提交失败"):
            delete_article_service(
                db=db,
                article_id=article_id,
                user_id=user.id,
            )

        assert rollback_called is True
    finally:
        db.close()

def test_update_article_service_success(test_db):
    from services.article_service import update_article_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="update_success_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="旧标题",
            content="旧内容",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        updated_article = update_article_service(
            db=db,
            article_id=article.id,
            title="新标题",
            content="新内容",
            user_id=user.id,
        )

        assert updated_article["title"] == "新标题"
        assert updated_article["content"] == "新内容"

        saved_article = db.query(Article).filter(
            Article.id == article.id
        ).first()

        assert updated_article["title"] == "新标题"
        assert updated_article["content"] == "新内容"
    finally:
        db.close()

def test_update_article_service_rollback(test_db, monkeypatch):
    from services.article_service import update_article_service
    from models import User

    db = test_db()
    rollback_called = False

    try:
        user = User(
            username="update_rollback_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="原始标题",
            content="原始内容",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id
        user_id = user.id

        def mock_commit():
            raise RuntimeError("模拟更新提交失败")

        def mock_rollback():
            nonlocal rollback_called
            rollback_called = True

        monkeypatch.setattr(db, "commit", mock_commit)
        monkeypatch.setattr(db, "rollback", mock_rollback)

        with pytest.raises(RuntimeError, match="模拟更新提交失败"):
            update_article_service(
                db=db,
                article_id=article_id,
                title="修改后的标题",
                content="修改后的内容",
                user_id=user_id,
            )

        assert rollback_called is True
    finally:
        db.close()

def test_get_articles_service_empty(test_db):
    from services.article_service import get_articles_service

    db = test_db()
    try:
        result = get_articles_service(
            db=db,
            page=1,
            size=10,
            keyword="不存在的关键词_xyz",
            sort="desc",
            user_id=1,
        )

        assert result["items"] == []
        assert result["page"] == 1
        assert result["size"] == 10
        assert result["total"] == 0
    finally:
        db.close()

def test_get_articles_service_keyword_search(test_db):
    from services.article_service import get_articles_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="search_test_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        articles = [
            Article(
                title="Python学习指南",
                content="介绍基础语法",
                user_id=user.id,
                is_deleted=False,
            ),
            Article(
                title="数据库入门",
                content="学习Python连接数据库",
                user_id=user.id,
                is_deleted=False,
            ),
            Article(
                title="旅行日记",
                content="记录一次旅行",
                user_id=user.id,
                is_deleted=False,
            ),
        ]
        db.add_all(articles)
        db.commit()

        # 搜索标题中包含 Python 的文章
        result = get_articles_service(
            db=db,
            page=1,
            size=10,
            keyword="Python",
            sort="desc",
            user_id=user.id,
        )

        assert result["total"] == 2
        assert len(result["items"]) == 2

        titles = {item["title"] for item in result["items"]}
        assert "Python学习指南" in titles
        assert "数据库入门" in titles
        assert "旅行日记" not in titles
    finally:
        db.close()

def test_get_articles_service_sort_by_views(test_db):
    from services.article_service import get_articles_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="sort_views_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        articles = [
            Article(
                title="低浏览量",
                content="测试内容",
                user_id=user.id,
                is_deleted=False,
                view_count=5,
            ),
            Article(
                title="高浏览量",
                content="测试内容",
                user_id=user.id,
                is_deleted=False,
                view_count=100,
            ),
            Article(
                title="中浏览量",
                content="测试内容",
                user_id=user.id,
                is_deleted=False,
                view_count=30,
            ),
        ]
        db.add_all(articles)
        db.commit()

        result = get_articles_service(
            db=db,
            page=1,
            size=10,
            keyword="",
            sort="views",
            user_id=user.id,
        )

        titles = [item["title"] for item in result["items"]]

        assert titles == ["高浏览量", "中浏览量", "低浏览量"]
    finally:
        db.close()

def test_get_articles_service_pagination(test_db):
    from services.article_service import get_articles_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="pagination_test_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        articles = [
            Article(
                title=f"分页文章{i}",
                content=f"内容{i}",
                user_id=user.id,
                is_deleted=False,
            )
            for i in range(1, 6)
        ]
        db.add_all(articles)
        db.commit()

        page1 = get_articles_service(
            db=db,
            page=1,
            size=2,
            keyword="",
            sort="desc",
            user_id=user.id,
        )

        page2 = get_articles_service(
            db=db,
            page=2,
            size=2,
            keyword="",
            sort="desc",
            user_id=user.id,
        )

        page3 = get_articles_service(
            db=db,
            page=3,
            size=2,
            keyword="",
            sort="desc",
            user_id=user.id,
        )

        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        assert len(page3["items"]) == 1

        assert page1["total"] == 5
        assert page2["total"] == 5
        assert page3["total"] == 5

        titles1 = {item["title"] for item in page1["items"]}
        titles2 = {item["title"] for item in page2["items"]}
        titles3 = {item["title"] for item in page3["items"]}

        assert titles1.isdisjoint(titles2)
        assert titles1.isdisjoint(titles3)
        assert titles2.isdisjoint(titles3)
    finally:
        db.close()

def test_get_articles_service_favorite_and_like_status(test_db):
    from services.article_service import get_articles_service
    from models import User, ArticleFavorite, ArticleLike

    db = test_db()
    try:
        user = User(
            username="status_test_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article1 = Article(
            title="已收藏并点赞",
            content="测试内容1",
            user_id=user.id,
            is_deleted=False,
        )
        article2 = Article(
            title="未收藏未点赞",
            content="测试内容2",
            user_id=user.id,
            is_deleted=False,
        )
        db.add_all([article1, article2])
        db.commit()
        db.refresh(article1)
        db.refresh(article2)

        db.add(ArticleFavorite(
            user_id=user.id,
            article_id=article1.id,
        ))
        db.add(ArticleLike(
            user_id=user.id,
            article_id=article1.id,
        ))
        db.commit()

        result = get_articles_service(
            db=db,
            page=1,
            size=10,
            keyword="",
            sort="desc",
            user_id=user.id,
        )

        items = {item["title"]: item for item in result["items"]}

        assert items["已收藏并点赞"]["is_favorited"] is True
        assert items["已收藏并点赞"]["is_liked"] is True
        assert items["未收藏未点赞"]["is_favorited"] is False
        assert items["未收藏未点赞"]["is_liked"] is False
    finally:
        db.close()

def test_get_article_service_stale_cache(test_db, monkeypatch):
    import json
    from services import article_service
    from services.article_service import get_article_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="stale_cache_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="数据库中的最新标题",
            content="数据库中的最新内容",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        stale_cache = {
            "id": article.id,
            "title": "缓存中的旧标题",
            "content": "缓存中的旧内容",
            "user_id": article.user_id,
            "username": user.username,
            "created_at": article.created_at.isoformat(),
            "updated_at": article.updated_at.isoformat(),
        }

        monkeypatch.setattr(
            article_service.redis_client,
            "get",
            lambda key: json.dumps(stale_cache),
        )

        cached_writes = []

        def mock_set(key, value, ex=None):
            cached_writes.append(json.loads(value))

        monkeypatch.setattr(
            article_service.redis_client,
            "set",
            mock_set,
        )

        result = get_article_service(
            db=db,
            article_id=article.id,
            user_id=user.id,
        )

        assert result["title"] == "数据库中的最新标题"
        assert result["content"] == "数据库中的最新内容"
        assert len(cached_writes) == 1
        assert cached_writes[0]["title"] == "数据库中的最新标题"
        assert cached_writes[0]["content"] == "数据库中的最新内容"
    finally:
        db.close()

def test_get_article_service_invalid_cache(test_db, monkeypatch):
    from services import article_service
    from services.article_service import get_article_service
    from models import User

    db = test_db()
    try:
        user = User(
            username="invalid_cache_user",
            password="test_password123",
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        article = Article(
            title="正常标题",
            content="正常内容",
            user_id=user.id,
            is_deleted=False,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        # 模拟 Redis 返回损坏的 JSON
        monkeypatch.setattr(
            article_service.redis_client,
            "get",
            lambda key: "{invalid-json",
        )

        cached_writes = []

        def mock_set(key, value, ex=None):
            cached_writes.append(value)

        monkeypatch.setattr(
            article_service.redis_client,
            "set",
            mock_set,
        )

        result = get_article_service(
            db=db,
            article_id=article.id,
            user_id=user.id,
        )

        assert result["title"] == "正常标题"
        assert result["content"] == "正常内容"
        assert len(cached_writes) == 1
    finally:
        db.close()

def test_get_article_service_view_count_per_user(test_db, monkeypatch):
    from services import article_service
    from services.article_service import get_article_service
    from models import User

    db = test_db()
    try:
        user1 = User(
            username="view_count_user1",
            password="test_password123",
            role="user",
        )
        user2 = User(
            username="view_count_user2",
            password="test_password123",
            role="user",
        )
        db.add_all([user1, user2])
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        article = Article(
            title="浏览量测试文章",
            content="测试重复浏览",
            user_id=user1.id,
            is_deleted=False,
            is_public=True,
            view_count=0,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        # 每次都绕过缓存，确保测试重点是浏览记录
        monkeypatch.setattr(
            article_service.redis_client,
            "get",
            lambda key: None,
        )
        monkeypatch.setattr(
            article_service.redis_client,
            "set",
            lambda *args, **kwargs: None,
        )

        article_id = article.id

        get_article_service(db, article_id, user1.id)
        db.refresh(article)
        assert article.view_count == 1

        get_article_service(db, article_id, user1.id)
        db.refresh(article)
        assert article.view_count == 1

        get_article_service(db, article_id, user2.id)
        db.refresh(article)
        assert article.view_count == 2
    finally:
        db.close()

def test_get_article_service_interaction_counts(test_db, monkeypatch):
    from services import article_service
    from services.article_service import get_article_service
    from models import (
        User,
        ArticleFavorite,
        ArticleLike,
        ArticleComment,
    )

    db = test_db()
    try:
        owner = User(
            username="count_owner",
            password="test_password123",
            role="user",
        )
        user2 = User(
            username="count_user2",
            password="test_password123",
            role="user",
        )
        user3 = User(
            username="count_user3",
            password="test_password123",
            role="user",
        )
        db.add_all([owner, user2, user3])
        db.commit()
        for user in (owner, user2, user3):
            db.refresh(user)

        article = Article(
            title="互动统计测试",
            content="测试收藏、点赞和评论数量",
            user_id=owner.id,
            is_deleted=False,
            view_count=0,
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        db.add_all([
            ArticleFavorite(user_id=owner.id, article_id=article.id),
            ArticleFavorite(user_id=user2.id, article_id=article.id),
            ArticleLike(user_id=owner.id, article_id=article.id),
            ArticleLike(user_id=user3.id, article_id=article.id),
            ArticleComment(
                user_id=owner.id,
                article_id=article.id,
                content="第一条评论",
            ),
            ArticleComment(
                user_id=user2.id,
                article_id=article.id,
                content="第二条评论",
            ),
        ])
        db.commit()

        monkeypatch.setattr(
            article_service.redis_client,
            "get",
            lambda key: None,
        )
        monkeypatch.setattr(
            article_service.redis_client,
            "set",
            lambda *args, **kwargs: None,
        )

        result = get_article_service(
            db=db,
            article_id=article.id,
            user_id=owner.id,
        )

        assert result["favorite_count"] == 2
        assert result["like_count"] == 2
        assert result["comment_count"] == 2
        assert result["is_favorited"] is True
        assert result["is_liked"] is True
    finally:
        db.close()

def test_get_my_articles_service_only_returns_own_articles(test_db):
    from models import Article
    from services.article_service import get_my_articles_service

    db = test_db()

    try:
        db.add_all([
            Article(
                title="用户1的文章",
                content="用户1的内容",
                user_id=1,
                is_deleted=False,
                view_count=0
            ),
            Article(
                title="用户2的文章",
                content="用户2的内容",
                user_id=2,
                is_deleted=False,
                view_count=0
            ),
        ])
        db.commit()

        result = get_my_articles_service(
            db=db,
            user_id=1,
            sort="desc",
            page=1,
            size=10,
            keyword=""
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "用户1的文章"

    finally:
        db.close()

def test_get_my_articles_service_keyword_and_deleted_filter(test_db):
    from models import Article
    from services.article_service import get_my_articles_service

    db = test_db()

    try:
        db.add_all([
            Article(
                title="Python入门",
                content="学习编程",
                user_id=1,
                is_deleted=False,
                view_count=0
            ),
            Article(
                title="Python进阶",
                content="高级编程",
                user_id=1,
                is_deleted=True,
                view_count=0
            ),
            Article(
                title="Python教程",
                content="其他用户的文章",
                user_id=2,
                is_deleted=False,
                view_count=0
            ),
        ])
        db.commit()

        result = get_my_articles_service(
            db=db,
            user_id=1,
            sort="desc",
            page=1,
            size=10,
            keyword="Python"
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Python入门"

    finally:
        db.close()

def test_get_my_articles_service_pagination(test_db):
    from models import Article
    from services.article_service import get_my_articles_service

    db = test_db()

    try:
        articles = [
            Article(
                title=f"测试文章{i}",
                content=f"内容{i}",
                user_id=1,
                is_deleted=False,
                view_count=0
            )
            for i in range(5)
        ]
        db.add_all(articles)
        db.commit()

        result = get_my_articles_service(
            db=db,
            user_id=1,
            sort="asc",
            page=2,
            size=2,
            keyword=""
        )

        assert result["total"] == 5
        assert result["page"] == 2
        assert result["size"] == 2
        assert len(result["items"]) == 2

    finally:
        db.close()

def test_get_my_articles_service_sort_by_views(test_db):
    from models import Article
    from services.article_service import get_my_articles_service

    db = test_db()

    try:
        db.add_all([
            Article(
                title="低浏览量文章",
                content="内容1",
                user_id=1,
                is_deleted=False,
                view_count=2
            ),
            Article(
                title="高浏览量文章",
                content="内容2",
                user_id=1,
                is_deleted=False,
                view_count=100
            ),
            Article(
                title="中浏览量文章",
                content="内容3",
                user_id=1,
                is_deleted=False,
                view_count=20
            ),
        ])
        db.commit()

        result = get_my_articles_service(
            db=db,
            user_id=1,
            sort="views",
            page=1,
            size=10,
            keyword=""
        )

        titles = [item["title"] for item in result["items"]]

        assert titles == [
            "高浏览量文章",
            "中浏览量文章",
            "低浏览量文章"
        ]

    finally:
        db.close()

def test_get_my_articles_service_default_sort_desc(test_db):
    from datetime import datetime, timedelta
    from models import Article
    from services.article_service import get_my_articles_service

    db = test_db()

    try:
        now = datetime(2025, 1, 1, 12, 0, 0)

        db.add_all([
            Article(
                title="较早的文章",
                content="内容1",
                user_id=1,
                is_deleted=False,
                view_count=0,
                created_at=now
            ),
            Article(
                title="较新的文章",
                content="内容2",
                user_id=1,
                is_deleted=False,
                view_count=0,
                created_at=now + timedelta(days=1)
            ),
        ])
        db.commit()

        result = get_my_articles_service(
            db=db,
            user_id=1,
            sort="unknown",
            page=1,
            size=10,
            keyword=""
        )

        titles = [item["title"] for item in result["items"]]

        assert titles == ["较新的文章", "较早的文章"]

    finally:
        db.close()

def test_admin_delete_article_service_success(test_db):
    from models import Article
    from services.article_service import admin_delete_article_service

    db = test_db()

    try:
        article = Article(
            title="管理员删除测试",
            content="测试软删除",
            user_id=1,
            is_deleted=False,
            view_count=0
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id

        result = admin_delete_article_service(
            db=db,
            article_id=article_id
        )

        assert result.id == article_id
        assert result.is_deleted is True

        db.refresh(article)
        assert article.is_deleted is True

    finally:
        db.close()

def test_admin_delete_article_service_not_found(test_db):
    from services.article_service import admin_delete_article_service
    from exceptions import NotFoundError

    db = test_db()

    try:
        with pytest.raises(NotFoundError):
            admin_delete_article_service(
                db=db,
                article_id=999999
            )
    finally:
        db.close()

def test_admin_delete_article_service_redis_error(test_db, monkeypatch):
    from models import Article
    from services import article_service

    db = test_db()

    try:
        article = Article(
            title="Redis异常测试",
            content="测试缓存清理失败",
            user_id=1,
            is_deleted=False,
            view_count=0
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        def mock_redis_delete(key):
            raise RuntimeError("Redis连接失败")

        monkeypatch.setattr(
            article_service.redis_client,
            "delete",
            mock_redis_delete
        )

        result = article_service.admin_delete_article_service(
            db=db,
            article_id=article.id
        )

        assert result.is_deleted is True

        db.refresh(article)
        assert article.is_deleted is True

    finally:
        db.close()

def test_admin_delete_article_service_rollback(test_db, monkeypatch):
    from models import Article
    from services import article_service

    db = test_db()

    try:
        article = Article(
            title="回滚测试文章",
            content="测试数据库提交失败",
            user_id=1,
            is_deleted=False,
            view_count=0
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id

        def mock_commit():
            raise RuntimeError("数据库提交失败")

        monkeypatch.setattr(db, "commit", mock_commit)

        with pytest.raises(RuntimeError, match="数据库提交失败"):
            article_service.admin_delete_article_service(
                db=db,
                article_id=article_id
            )

        db.rollback()

        saved_article = db.query(Article).filter(
            Article.id == article_id
        ).first()

        assert saved_article.is_deleted is False

    finally:
        db.close()

def test_restore_article_service_success(test_db, monkeypatch):
    from models import Article
    from services import article_service

    db = test_db()

    try:
        article = Article(
            title="待恢复文章",
            content="测试文章恢复",
            user_id=1,
            is_deleted=True,
            view_count=0
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id

        monkeypatch.setattr(
            article_service.redis_client,
            "delete",
            lambda key: 1
        )

        result = article_service.restore_article_service(
            db=db,
            article_id=article_id
        )

        assert result.id == article_id
        assert result.is_deleted is False

        db.refresh(article)
        assert article.is_deleted is False

    finally:
        db.close()

def test_restore_article_service_not_found(test_db):
    from services.article_service import restore_article_service
    from exceptions import NotFoundError

    db = test_db()

    try:
        with pytest.raises(NotFoundError):
            restore_article_service(
                db=db,
                article_id=999999
            )
    finally:
        db.close()

def test_restore_article_service_rollback(test_db, monkeypatch):
    from models import Article
    from services import article_service

    db = test_db()

    try:
        article = Article(
            title="回滚测试文章",
            content="测试数据库提交失败",
            user_id=1,
            is_deleted=True,
            view_count=0
        )
        db.add(article)
        db.commit()
        db.refresh(article)

        article_id = article.id

        def fake_commit():
            raise RuntimeError("模拟数据库提交失败")

        monkeypatch.setattr(db, "commit", fake_commit)

        with pytest.raises(RuntimeError):
            article_service.restore_article_service(
                db=db,
                article_id=article_id
            )

        db.rollback()

        db.expire_all()

        saved_article = db.query(Article).filter(
            Article.id == article_id
        ).first()

        assert saved_article.is_deleted is True

    finally:
        db.close()


def test_pending_cleanup_task_retries_successfully(test_db, monkeypatch):
    from models import VectorCleanupTask
    from rag.cleanup_tasks import process_pending_cleanup_tasks
    import rag.vector_store as vector_store_module

    # 创建一条等待处理的清理任务
    db = test_db()
    try:
        task = VectorCleanupTask(
            article_id=987654,
            status="pending",
            retry_count=0,
            last_error="模拟之前清理失败",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()

    # 模拟向量清理成功，避免真的修改 ChromaDB
    calls = []

    def fake_delete(article_id):
        calls.append(article_id)

    monkeypatch.setattr(
        vector_store_module.vector_store,
        "delete_by_article_id",
        fake_delete,
    )

    # 执行一轮后台任务
    processed = process_pending_cleanup_tasks(
        test_db,
        max_retries=5,
        batch_size=20,
    )

    # 验证任务确实执行并成功完成
    assert processed == 1
    assert calls == [987654]

    db = test_db()
    try:
        saved_task = (
            db.query(VectorCleanupTask)
            .filter(VectorCleanupTask.id == task_id)
            .first()
        )

        assert saved_task is not None
        assert saved_task.status == "completed"
        assert saved_task.last_error is None
        assert saved_task.retry_count == 0
    finally:
        db.close()


def test_pending_cleanup_task_marks_failed_after_retry_limit(test_db):
    from models import VectorCleanupTask
    from rag.cleanup_tasks import process_pending_cleanup_tasks

    db = test_db()
    try:
        task = VectorCleanupTask(
            article_id=987655,
            status="pending",
            retry_count=5,
            last_error="之前多次清理失败",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()

    # 设置最大重试次数为 5；已达到上限的任务应被标记为 failed
    process_pending_cleanup_tasks(
        test_db,
        max_retries=5,
        batch_size=20,
    )

    db = test_db()
    try:
        saved_task = (
            db.query(VectorCleanupTask)
            .filter(VectorCleanupTask.id == task_id)
            .first()
        )

        assert saved_task is not None
        assert saved_task.status == "failed"
        assert saved_task.retry_count == 5
    finally:
        db.close()


def test_cleanup_task_only_one_worker_can_claim_it(test_db):
    from models import VectorCleanupTask
    from rag.cleanup_tasks import retry_cleanup_task

    # 创建一条待处理的补偿任务
    db = test_db()
    try:
        task = VectorCleanupTask(
            article_id=987656,
            status="pending",
            retry_count=0,
            last_error="测试并发领取",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id
    finally:
        db.close()

    # 第一个会话先领取任务，将状态改为 processing
    db1 = test_db()
    try:
        claimed = (
            db1.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.id == task_id,
                VectorCleanupTask.status == "pending",
            )
            .update(
                {VectorCleanupTask.status: "processing"},
                synchronize_session=False,
            )
        )
        db1.commit()
        assert claimed == 1
    finally:
        db1.close()

    # 第二个会话再尝试领取同一任务，应该领取失败
    db2 = test_db()
    try:
        result = retry_cleanup_task(db2, task_id)
        assert result is False
    finally:
        db2.close()

    # 最终任务仍然只能由第一个会话领取
    db = test_db()
    try:
        saved_task = (
            db.query(VectorCleanupTask)
            .filter(VectorCleanupTask.id == task_id)
            .first()
        )
        assert saved_task is not None
        assert saved_task.status == "processing"
    finally:
        db.close()

