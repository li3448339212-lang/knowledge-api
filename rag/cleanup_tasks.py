from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session

from models import VectorCleanupTask

logger = logging.getLogger(__name__)


def create_cleanup_task(
    db: Session,
    article_id: int,
    error_message: str,
) -> None:
    """记录需要重试的向量清理任务。"""
    task = VectorCleanupTask(
        article_id=int(article_id),
        status="pending",
        retry_count=0,
        last_error=error_message[:5000],
    )

    try:
        db.add(task)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "保存向量清理任务失败, article_id=%s",
            article_id,
        )
        raise



def retry_cleanup_task(db: Session, task_id: int) -> bool:
    """领取并重试指定的向量清理任务。"""
    from rag.vector_store import vector_store

    try:
        # 原子领取任务：只有 pending 状态才能改为 processing
        claimed = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.id == task_id,
                VectorCleanupTask.status == "pending",
            )
            .update(
                {VectorCleanupTask.status: "processing"},
                synchronize_session=False,
            )
        )
        db.commit()

        if claimed == 0:
            return False

        task = (
            db.query(VectorCleanupTask)
            .filter(VectorCleanupTask.id == task_id)
            .first()
        )

        if task is None:
            return False

        article_id = task.article_id

        vector_store.delete_by_article_id(article_id)

        task.status = "completed"
        task.last_error = None
        db.commit()
        return True

    except Exception as exc:
        db.rollback()

        try:
            task = (
                db.query(VectorCleanupTask)
                .filter(VectorCleanupTask.id == task_id)
                .first()
            )

            if task is not None:
                task.retry_count += 1
                task.last_error = str(exc)[:5000]
                task.status = "pending"
                db.commit()

        except Exception:
            db.rollback()
            logger.exception(
                "更新向量清理任务失败状态时发生异常, task_id=%s",
                task_id,
            )

        logger.exception(
            "向量清理重试失败, task_id=%s",
            task_id,
        )
        return False






def process_pending_cleanup_tasks(
    session_factory,
    max_retries: int = 5,
    batch_size: int = 20,
) -> int:
    """扫描待处理任务、恢复超时任务并自动重试。"""
    processed = 0
    db = session_factory()

    try:
        # 1. 恢复超过 10 分钟仍处于 processing 的任务
        timeout_before = datetime.now() - timedelta(minutes=10)

        stuck_ids = [
            task_id
            for (task_id,) in (
                db.query(VectorCleanupTask.id)
                .filter(
                    VectorCleanupTask.status == "processing",
                    VectorCleanupTask.updated_at < timeout_before,
                )
                .order_by(VectorCleanupTask.id.asc())
                .limit(batch_size)
                .all()
            )
        ]

        if stuck_ids:
            (
                db.query(VectorCleanupTask)
                .filter(
                    VectorCleanupTask.id.in_(stuck_ids),
                    VectorCleanupTask.status == "processing",
                    VectorCleanupTask.updated_at < timeout_before,
                )
                .update(
                    {VectorCleanupTask.status: "pending"},
                    synchronize_session=False,
                )
            )
            db.commit()

            logger.warning(
                "已恢复超时的向量清理任务：%s",
                len(stuck_ids),
            )

        # 2. 将达到重试上限的待处理任务标记为失败
        exhausted_ids = [
            task_id
            for (task_id,) in (
                db.query(VectorCleanupTask.id)
                .filter(
                    VectorCleanupTask.status == "pending",
                    VectorCleanupTask.retry_count >= max_retries,
                )
                .order_by(VectorCleanupTask.id.asc())
                .limit(batch_size)
                .all()
            )
        ]

        if exhausted_ids:
            (
                db.query(VectorCleanupTask)
                .filter(
                    VectorCleanupTask.id.in_(exhausted_ids),
                    VectorCleanupTask.status == "pending",
                )
                .update(
                    {VectorCleanupTask.status: "failed"},
                    synchronize_session=False,
                )
            )
            db.commit()

            logger.info(
                "达到重试上限并标记为失败的任务数：%s",
                len(exhausted_ids),
            )

        # 3. 查询尚未达到重试上限的待处理任务
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

    # 4. 使用独立会话处理每条任务
    for task_id in task_ids:
        task_db = session_factory()

        try:
            success = retry_cleanup_task(task_db, task_id)

            if success:
                processed += 1
            else:
                logger.warning(
                    "向量清理任务未成功完成，task_id=%s",
                    task_id,
                )

        except Exception:
            logger.exception(
                "处理向量清理任务时发生异常，task_id=%s",
                task_id,
            )
        finally:
            task_db.close()

    return processed
