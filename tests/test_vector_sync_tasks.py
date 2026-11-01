from models import Article, VectorSyncTask
from rag.cleanup_tasks import process_pending_sync_tasks


def test_pending_sync_task_retries_successfully(test_db, monkeypatch):
    db = test_db()
    # 1. 创建一篇文章
    article = Article(
        title="测试文章",
        content="这是一篇用于测试向量同步的文章。",
        user_id=1,
        is_deleted=False,
    )
    db.add(article)
    db.commit()
    db.refresh(article)

    # 2. 创建一个待同步任务
    task = VectorSyncTask(
        article_id=article.id,
        status="pending",
        retry_count=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 3. 模拟向量同步成功
    def fake_update_article(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "rag.vector_store.vector_store.update_article",
        fake_update_article,
    )

    # 4. 执行同步任务
    processed = process_pending_sync_tasks(
        session_factory=test_db,
        max_retries=5,
        batch_size=20,
    )

    # 5. 检查任务是否成功
    db.refresh(task)

    assert processed == 1
    assert task.status == "completed"
    assert task.retry_count == 0
    assert task.last_error is None

def test_pending_sync_task_retries_after_failure(test_db, monkeypatch):
    db = test_db()

    article = Article(
        title="同步失败测试",
        content="用于测试同步失败后的重试。",
        user_id=1,
        is_deleted=False,
    )
    db.add(article)
    db.commit()
    db.refresh(article)

    task = VectorSyncTask(
        article_id=article.id,
        status="pending",
        retry_count=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # 模拟 ChromaDB 同步失败
    def fake_update_article(*args, **kwargs):
        raise RuntimeError("模拟向量同步失败")

    monkeypatch.setattr(
        "rag.vector_store.vector_store.update_article",
        fake_update_article,
    )

    processed = process_pending_sync_tasks(
        session_factory=test_db,
        max_retries=5,
        batch_size=20,
    )

    db.refresh(task)

    assert processed == 1
    assert task.status == "pending"
    assert task.retry_count == 1
    assert "模拟向量同步失败" in task.last_error

def test_pending_sync_task_marks_failed_after_retry_limit(test_db):
    db = test_db()

    task = VectorSyncTask(
        article_id=999999,
        status="pending",
        retry_count=5,
        last_error="之前同步失败",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    processed = process_pending_sync_tasks(
        session_factory=test_db,
        max_retries=5,
        batch_size=20,
    )

    db.refresh(task)

    assert processed == 0
    assert task.status == "failed"
    assert task.retry_count == 5