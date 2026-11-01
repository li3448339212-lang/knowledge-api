from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Article, VectorCleanupTask, VectorSyncTask
import uuid

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

def create_vector_sync_task(
    db: Session,
    article_id: int,
    error_message: str,
) -> None:
    """记录需要重试的文章向量同步任务。"""

    task = VectorSyncTask(
        article_id=int(article_id),
        status="pending",
        retry_count=0,
        last_error=error_message[:5000],
    )

    try:
        db.add(task)
        db.commit()

        logger.info(
            "已创建文章向量同步任务，article_id=%s",
            article_id,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "保存文章向量同步任务失败，article_id=%s",
            article_id,
        )
        raise



def retry_cleanup_task(db: Session, task_id: int) -> bool:
    """领取并重试指定的向量清理任务。"""
    from rag.vector_store import vector_store

    lease_token = str(uuid.uuid4())

    try:
        # 1. 原子领取任务
        claimed = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.id == task_id,
                VectorCleanupTask.status == "pending",
            )
            .update(
                {
                    VectorCleanupTask.status: "processing",
                    VectorCleanupTask.locked_at: func.now(),
                    VectorCleanupTask.updated_at: func.now(),
                    VectorCleanupTask.lease_token: lease_token,
                },
                synchronize_session=False,
            )
        )
        db.commit()

        # 任务没有领取成功
        if claimed == 0:
            return False

        # 2. 只读取当前租约持有者领取的任务
        task = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.id == task_id,
                VectorCleanupTask.status == "processing",
                VectorCleanupTask.lease_token == lease_token,
            )
            .first()
        )

        # 领取成功后读取失败，释放当前租约
        if task is None:
            db.rollback()

            released = (
                db.query(VectorCleanupTask)
                .filter(
                    VectorCleanupTask.id == task_id,
                    VectorCleanupTask.status == "processing",
                    VectorCleanupTask.lease_token == lease_token,
                )
                .update(
                    {
                        VectorCleanupTask.status: "pending",
                        VectorCleanupTask.locked_at: None,
                        VectorCleanupTask.lease_token: None,
                        VectorCleanupTask.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

            logger.warning(
                "任务领取后读取失败，已尝试释放当前租约，"
                "task_id=%s, released=%s",
                task_id,
                released,
            )
            return False

        article_id = task.article_id

        # 3. 执行 Chroma 向量清理
        vector_store.delete_by_article_id(article_id)

        # 4. 只有当前租约持有者才能标记任务完成
        updated = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.id == task_id,
                VectorCleanupTask.status == "processing",
                VectorCleanupTask.lease_token == lease_token,
            )
            .update(
                {
                    VectorCleanupTask.status: "completed",
                    VectorCleanupTask.last_error: None,
                    VectorCleanupTask.locked_at: None,
                    VectorCleanupTask.lease_token: None,
                    VectorCleanupTask.updated_at: func.now(),
                },
                synchronize_session=False,
            )
        )
        db.commit()

        return updated == 1

    except Exception as exc:
        # 5. 清理执行失败，回滚当前事务
        db.rollback()

        try:
            # 只有当前租约持有者才能更新失败状态
            updated = (
                db.query(VectorCleanupTask)
                .filter(
                    VectorCleanupTask.id == task_id,
                    VectorCleanupTask.status == "processing",
                    VectorCleanupTask.lease_token == lease_token,
                )
                .update(
                    {
                        VectorCleanupTask.retry_count:
                            VectorCleanupTask.retry_count + 1,
                        VectorCleanupTask.last_error: str(exc)[:5000],
                        VectorCleanupTask.status: "pending",
                        VectorCleanupTask.locked_at: None,
                        VectorCleanupTask.lease_token: None,
                        VectorCleanupTask.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

            if updated == 0:
                logger.warning(
                    "任务租约已失效，跳过旧进程的失败状态更新，"
                    "task_id=%s",
                    task_id,
                )

        except Exception:
            db.rollback()
            logger.exception(
                "更新向量清理任务失败状态时发生异常，task_id=%s",
                task_id,
            )

        logger.exception(
            "向量清理重试失败，task_id=%s",
            task_id,
        )
        return False

def retry_vector_sync_task(db: Session, task_id: int) -> bool:
    """领取并重试指定的文章向量同步任务。"""

    lease_token = str(uuid.uuid4())

    try:
        # 1. 原子领取任务
        claimed = (
            db.query(VectorSyncTask)
            .filter(
                VectorSyncTask.id == task_id,
                VectorSyncTask.status == "pending",
            )
            .update(
                {
                    VectorSyncTask.status: "processing",
                    VectorSyncTask.locked_at: func.now(),
                    VectorSyncTask.updated_at: func.now(),
                    VectorSyncTask.lease_token: lease_token,
                },
                synchronize_session=False,
            )
        )
        db.commit()

        if claimed == 0:
            return False

        # 2. 读取当前租约持有者领取的任务
        task = (
            db.query(VectorSyncTask)
            .filter(
                VectorSyncTask.id == task_id,
                VectorSyncTask.status == "processing",
                VectorSyncTask.lease_token == lease_token,
            )
            .first()
        )

        if task is None:
            db.rollback()

            # 释放当前任务的租约，避免任务一直处于 processing
            released = (
                db.query(VectorSyncTask)
                .filter(
                    VectorSyncTask.id == task_id,
                    VectorSyncTask.status == "processing",
                    VectorSyncTask.lease_token == lease_token,
                )
                .update(
                    {
                        VectorSyncTask.status: "pending",
                        VectorSyncTask.locked_at: None,
                        VectorSyncTask.lease_token: None,
                        VectorSyncTask.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )

            db.commit()

            logger.warning(
                "向量同步任务领取后读取失败，已尝试释放租约，"
                "task_id=%s, released=%s",
                task_id,
                released,
            )

            return False

        article_id = task.article_id

        # 3. 从 MySQL 读取文章
        article = (
            db.query(Article)
            .filter(
                Article.id == article_id,
                Article.is_deleted == False,
            )
            .first()
        )

        if article is None:
            raise ValueError(
                f"文章不存在或已删除，article_id={article_id}"
            )

        # 4. 重新切分文章并同步 ChromaDB
        from rag.text_splitter import text_splitter
        from rag.vector_store import vector_store

        chunks = text_splitter.split_text(article.content)

        vector_store.update_article(
            chunks,
            article_id=article.id,
            user_id=article.user_id,
            is_public=article.is_public,
        )

        # 5. 只有当前租约持有者才能标记完成
        updated = (
            db.query(VectorSyncTask)
            .filter(
                VectorSyncTask.id == task_id,
                VectorSyncTask.status == "processing",
                VectorSyncTask.lease_token == lease_token,
            )
            .update(
                {
                    VectorSyncTask.status: "completed",
                    VectorSyncTask.last_error: None,
                    VectorSyncTask.locked_at: None,
                    VectorSyncTask.lease_token: None,
                    VectorSyncTask.updated_at: func.now(),
                },
                synchronize_session=False,
            )
        )
        db.commit()

        return updated == 1

    except Exception as exc:
        db.rollback()

        try:
            updated = (
                db.query(VectorSyncTask)
                .filter(
                    VectorSyncTask.id == task_id,
                    VectorSyncTask.status == "processing",
                    VectorSyncTask.lease_token == lease_token,
                )
                .update(
                    {
                        VectorSyncTask.retry_count:
                            VectorSyncTask.retry_count + 1,
                        VectorSyncTask.last_error: str(exc)[:5000],
                        VectorSyncTask.status: "pending",
                        VectorSyncTask.locked_at: None,
                        VectorSyncTask.lease_token: None,
                        VectorSyncTask.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

            if updated == 0:
                logger.warning(
                    "向量同步任务租约已失效，跳过旧进程的失败状态更新，"
                    "task_id=%s",
                    task_id,
                )

        except Exception:
            db.rollback()
            logger.exception(
                "更新向量同步任务失败状态时发生异常，task_id=%s",
                task_id,
            )

        logger.exception(
            "文章向量同步重试失败，task_id=%s",
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
                    VectorCleanupTask.locked_at.isnot(None),
                    VectorCleanupTask.locked_at < timeout_before,
                    VectorCleanupTask.retry_count < max_retries,
                )
                .order_by(VectorCleanupTask.id.asc())
                .limit(batch_size)
                .all()
            )
        ]

        if stuck_ids:
            recovered_count = (
                db.query(VectorCleanupTask)
                .filter(
                    VectorCleanupTask.id.in_(stuck_ids),
                    VectorCleanupTask.status == "processing",
                    VectorCleanupTask.locked_at.isnot(None),
                    VectorCleanupTask.locked_at < timeout_before,
                    VectorCleanupTask.retry_count < max_retries,
                )
                .update(
                    {
                        VectorCleanupTask.status: "pending",
                        VectorCleanupTask.lease_token: None,
                        VectorCleanupTask.locked_at: None,
                        VectorCleanupTask.updated_at: func.now(),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

            logger.warning(
                "已恢复超时的向量清理任务：%s",
                recovered_count,
            )

        # 将超时且达到重试上限的任务直接标记为失败
        exhausted_stuck_count = (
            db.query(VectorCleanupTask)
            .filter(
                VectorCleanupTask.status == "processing",
                VectorCleanupTask.locked_at.isnot(None),
                VectorCleanupTask.locked_at < timeout_before,
                VectorCleanupTask.retry_count >= max_retries,
            )
            .update(
                {
                    VectorCleanupTask.status: "failed",
                    VectorCleanupTask.locked_at: None,
                    VectorCleanupTask.lease_token: None,
                    VectorCleanupTask.updated_at: func.now(),
                },
                synchronize_session=False,
            )
        )
        db.commit()

        if exhausted_stuck_count:
            logger.warning(
                "超时且达到重试上限的任务已标记为失败：%s",
                exhausted_stuck_count,
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
            failed_count = (
                db.query(VectorCleanupTask)
                .filter(
                    VectorCleanupTask.id.in_(exhausted_ids),
                    VectorCleanupTask.status == "pending",
                    VectorCleanupTask.retry_count >= max_retries,
                )
                .update(
                    {VectorCleanupTask.status: "failed"},
                    synchronize_session=False,
                )
            )
            db.commit()

            logger.info(
                "达到重试上限并标记为失败的任务数：%s",
                failed_count,
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

def process_pending_sync_tasks(
    session_factory,
    max_retries: int = 5,
    batch_size: int = 20,
) -> int:
    """扫描并处理待同步的文章向量任务。"""

    db = session_factory()

    try:
        # 1. 恢复超时的 processing 任务
        timeout_time = datetime.now() - timedelta(minutes=10)

        db.query(VectorSyncTask).filter(
            VectorSyncTask.status == "processing",
            VectorSyncTask.locked_at <= timeout_time,
        ).update(
            {
                VectorSyncTask.status: "pending",
                VectorSyncTask.locked_at: None,
                VectorSyncTask.lease_token: None,
                VectorSyncTask.updated_at: func.now(),
            },
            synchronize_session=False,
        )

        db.commit()

        # 2. 将达到重试上限的任务标记为 failed
        db.query(VectorSyncTask).filter(
            VectorSyncTask.status == "pending",
            VectorSyncTask.retry_count >= max_retries,
        ).update(
            {
                VectorSyncTask.status: "failed",
                VectorSyncTask.updated_at: func.now(),
            },
            synchronize_session=False,
        )

        db.commit()

        # 3. 查询本轮需要处理的任务
        task_ids = [
            task.id
            for task in (
                db.query(VectorSyncTask)
                .filter(
                    VectorSyncTask.status == "pending",
                    VectorSyncTask.retry_count < max_retries,
                )
                .order_by(VectorSyncTask.created_at.asc())
                .limit(batch_size)
                .all()
            )
        ]

        # 4. 逐条执行同步任务
        processed = 0

        for task_id in task_ids:
            success = retry_vector_sync_task(db, task_id)

            if success:
                processed += 1
            else:
                logger.warning(
                    "文章向量同步任务未成功完成，task_id=%s",
                    task_id,
                )

        logger.info(
            "本轮文章向量同步任务处理结束，处理数量：%s",
            processed,
        )

        return processed

    except Exception:
        db.rollback()
        logger.exception("扫描文章向量同步任务时发生异常")
        raise

    finally:
        db.close()