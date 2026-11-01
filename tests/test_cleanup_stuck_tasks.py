
from datetime import datetime, timedelta

from database import SessionLocal
from models import VectorCleanupTask
from rag.cleanup_tasks import process_pending_cleanup_tasks


def test_stuck_processing_task_returns_to_pending():
    db = SessionLocal()
    task_id = None

    try:
        task = VectorCleanupTask(
            article_id=999997,
            status="processing",
            retry_count=1,
            last_error="模拟任务中断",
            locked_at=datetime.now() - timedelta(minutes=15),
            updated_at=datetime.now() - timedelta(minutes=15),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    finally:
        db.close()

    try:
        # 执行扫描；恢复后的任务可能会在同一轮被重试
        process_pending_cleanup_tasks(
            SessionLocal,
            max_retries=5,
            batch_size=20,
        )

        check_db = SessionLocal()
        try:
            task = (
                check_db.query(VectorCleanupTask)
                .filter(VectorCleanupTask.id == task_id)
                .first()
            )
            assert task is not None
            assert task.status in ("pending", "completed", "failed")
            assert task.status != "processing"

        finally:
            check_db.close()

    finally:
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
