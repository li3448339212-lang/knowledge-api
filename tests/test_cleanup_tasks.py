
from unittest.mock import patch

from database import SessionLocal
from models import VectorCleanupTask
from rag.cleanup_tasks import retry_cleanup_task


def test_retry_failure_increments_retry_count():
    db = SessionLocal()

    try:
        task = VectorCleanupTask(
            article_id=999999,
            status="pending",
            retry_count=0,
            last_error=None,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

        with patch(
            "rag.vector_store.vector_store.delete_by_article_id",
            side_effect=RuntimeError("模拟向量清理失败"),
        ):
            result = retry_cleanup_task(db, task_id)

        db.refresh(task)

        assert result is False
        assert task.retry_count == 1
        assert task.last_error == "模拟向量清理失败"

    finally:
        # 只清理本测试创建的任务记录
        db.rollback()
        db.query(VectorCleanupTask).filter(
            VectorCleanupTask.article_id == 999999,
            VectorCleanupTask.last_error == "模拟向量清理失败",
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
