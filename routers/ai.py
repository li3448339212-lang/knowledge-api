from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from security import get_current_user
from rag.rag_engine import rag_engine

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    session_id: str = "default"

class ConfirmArticleRequest(BaseModel):
    confirmation_id: str


@router.post("/ask")
async def ask_ai(
    request: AskRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    AI 知识库问答接口（支持多轮对话 + 用户身份鉴权）
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    # 把真实用户的 ID 传给 RAG 引擎
    result = rag_engine.ask(
        request.question,
        session_id=request.session_id,
        user_id=current_user["user_id"]
    )
    return {
        "code": 200,
        "message": "success",
        "data": result
    }


@router.post("/confirm-create")
async def confirm_article(
    request: ConfirmArticleRequest,
    current_user: dict = Depends(get_current_user)
):
    """用户确认后，才真正创建文章。"""
    print("当前登录用户 ID：", current_user["user_id"])
    result = rag_engine.confirm_article_creation(
        confirmation_id=request.confirmation_id,
        user_id=current_user["user_id"],
    )

    if result.startswith(("确认失败：", "创建文章失败：")):
        raise HTTPException(status_code=400, detail=result)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "answer": result
        }
    }
