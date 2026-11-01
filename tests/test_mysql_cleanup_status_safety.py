
from unittest.mock import patch

from models import VectorCleanupTask
from rag.cleanup_tasks import retry_cleanup_task
from tests.mysql_test_config import TestingSessionLocal, create_test_tables


def test_cleanup_failure_does_not_overwrite_failed_status():
    create_test_tables()

    # 创建一条待处理任务
    with TestingSessionLocal() as db:
        task = VectorCleanupTask(
            article_id=987654322,
            status="pending",
            retry_count=0,
            last_error="状态保护测试",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    def change_status_then_fail(article_id):
        # 模拟另一个流程先将任务标记为 failed
        with TestingSessionLocal() as other_db:
            other_task = other_db.get(VectorCleanupTask, task_id)
            other_task.status = "failed"
            other_db.commit()

        # 再模拟向量清理失败
        raise RuntimeError("模拟向量清理失败")

    try:
        with patch(
            "rag.vector_store.vector_store.delete_by_article_id",
            side_effect=change_status_then_fail,
        ):
            with TestingSessionLocal() as db:
                result = retry_cleanup_task(db, task_id)
                assert result is False

        # 检查 failed 状态有没有被覆盖
        with TestingSessionLocal() as db:
            task = db.get(VectorCleanupTask, task_id)
            assert task.status == "failed"
            assert task.retry_count == 0

    finally:
        with TestingSessionLocal() as db:
            task = db.get(VectorCleanupTask, task_id)
            if task is not None:
                db.delete(task)
                db.commit()


def test_old_lease_does_not_overwrite_new_lease():
    create_test_tables()

    # 创建一条待处理任务
    with TestingSessionLocal() as db:
        task = VectorCleanupTask(
            article_id=987654323,
            status="pending",
            retry_count=0,
            last_error="旧租约测试",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    new_lease_token = "new-lease-token"

    def replace_lease_then_fail(article_id):
        # 模拟任务超时恢复后，被另一个工作进程重新领取
        with TestingSessionLocal() as other_db:
            other_task = other_db.get(VectorCleanupTask, task_id)

            assert other_task.status == "processing"

            other_task.lease_token = new_lease_token
            other_db.commit()

        # 模拟旧工作进程随后发生异常
        raise RuntimeError("模拟旧工作进程失败")

    try:
        with patch(
            "rag.vector_store.vector_store.delete_by_article_id",
            side_effect=replace_lease_then_fail,
        ):
            with TestingSessionLocal() as db:
                result = retry_cleanup_task(db, task_id)
                assert result is False

        # 检查旧租约是否错误修改了新租约的任务
        with TestingSessionLocal() as db:
            task = db.get(VectorCleanupTask, task_id)

            assert task.status == "processing"
            assert task.retry_count == 0
            assert task.lease_token == new_lease_token

    finally:
        with TestingSessionLocal() as db:
            task = db.get(VectorCleanupTask, task_id)
            if task is not None:
                db.delete(task)
                db.commit()
