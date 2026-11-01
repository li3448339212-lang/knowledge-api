
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from models import VectorCleanupTask
from tests.mysql_test_config import TestingSessionLocal, create_test_tables


def test_mysql_only_one_worker_claims_task():
    create_test_tables()

    # 创建一条专用测试任务
    with TestingSessionLocal() as db:
        task = VectorCleanupTask(
            article_id=987654321,
            status="pending",
            retry_count=0,
            last_error="MySQL 并发测试",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    # 两个线程同时开始执行条件更新
    barrier = Barrier(2)

    def claim_task():
        with TestingSessionLocal() as db:
            barrier.wait()

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
            return claimed

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: claim_task(), range(2)))

        assert sorted(results) == [0, 1]

        with TestingSessionLocal() as db:
            task = db.get(VectorCleanupTask, task_id)
            assert task.status == "processing"
    finally:
        with TestingSessionLocal() as db:
            task = db.get(VectorCleanupTask, task_id)
            if task is not None:
                db.delete(task)
                db.commit()
