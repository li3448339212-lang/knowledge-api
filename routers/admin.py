
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from security import get_admin_user
from models import VectorCleanupTask
from rag.cleanup_tasks import retry_cleanup_task

router = APIRouter(prefix="/admin", tags=["管理员"])
logger = logging.getLogger(__name__)



@router.post("/vector-cleanup/{task_id}/retry")
def retry_vector_cleanup(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user),
):
    task = (
        db.query(VectorCleanupTask)
        .filter(VectorCleanupTask.id == task_id)
        .first()
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="清理任务不存在",
        )

    if task.status not in {"pending", "failed"}:
        raise HTTPException(
            status_code=400,
            detail="只有待处理或失败的任务可以重试",
        )

    # 失败任务重新进入待处理状态
    if task.status == "failed":
        task.status = "pending"
        task.retry_count = 0
        task.last_error = None
        db.commit()

    success = retry_cleanup_task(db, task_id)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="向量清理重试失败，请查看服务器日志",
        )

    return {
        "message": "向量清理成功",
        "task_id": task_id,
    }



@router.get("/vector-cleanup/tasks")
def list_vector_cleanup_tasks(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user),
):
    query = db.query(VectorCleanupTask)

    if status is not None:
        allowed_statuses = {
            "pending",
            "processing",
            "completed",
            "failed",
        }
        if status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail="状态只能是 pending、processing、completed 或 failed",
            )
        query = query.filter(VectorCleanupTask.status == status)

    tasks = (
        query.order_by(VectorCleanupTask.id.desc())
        .limit(100)
        .all()
    )

    return [
        {
            "id": task.id,
            "article_id": task.article_id,
            "status": task.status,
            "retry_count": task.retry_count,
            "last_error": task.last_error,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
        for task in tasks
    ]
