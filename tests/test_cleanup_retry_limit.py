
from database import SessionLocal
from models import VectorCleanupTask
from rag.cleanup_tasks import process_pending_cleanup_tasks


def test_retry_limit_marks_task_failed():
    db = SessionLocal()
    task_id = None

    try:
        task = VectorCleanupTask(
            article_id=999998,
            status="pending",
            retry_count=5,
            last_error="测试失败",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    finally:
        db.close()

    try:
        processed = process_pending_cleanup_tasks(
            SessionLocal,
            max_retries=5,
            batch_size=20,
        )

        # 使用新的数据库会话检查更新后的状态
        check_db = SessionLocal()
        try:
            task = (
                check_db.query(VectorCleanupTask)
                .filter(VectorCleanupTask.id == task_id)
                .first()
            )

            assert task is not None
            assert task.status == "failed"
            assert processed == 0

        finally:
            check_db.close()

    finally:
        # 清理测试数据
        cleanup_db = SessionLocal()
        try:
            if task_id is not None:
                (
                    cleanup_db.query(VectorCleanupTask)
                    .filter(VectorCleanupTask.id == task_id)
                    .delete(synchronize_session=False)
                )
                cleanup_db.commit()
        finally:
            cleanup_db.close()
