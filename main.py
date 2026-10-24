from routers import ai
import time
from rag.data_loader import load_articles_to_vector_store
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from routers.users import router as users_router
from routers.articles import router as articles_router

from exceptions import (
    NotFoundError,
    PermissionDeniedError,
    BadRequestError,
    UnauthorizedError,
    not_found_exception_handler,
    permission_denied_exception_handler,
    bad_request_exception_handler,
    unauthorized_exception_handler,
)
from routers.admin import router as admin_router
import asyncio
import logging
from contextlib import asynccontextmanager
from logger import logger
from database import SessionLocal
from rag.cleanup_tasks import process_pending_cleanup_tasks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n🚀 FastAPI 正在启动，正在初始化 RAG 知识库...")
    await asyncio.to_thread(load_articles_to_vector_store)
    print("✅ RAG 知识库初始化完成！\n")

    async def cleanup_worker():
        while True:
            logger.info("向量清理后台任务开始执行")

            try:
                count = await asyncio.to_thread(
                    process_pending_cleanup_tasks,
                    SessionLocal,
                )
                if count:
                    logger.info(
                        "本轮处理了 %s 个向量清理任务",
                        count,
                    )
            except Exception:
                logger.exception("向量清理定时任务发生异常")

            await asyncio.sleep(60)
    worker = asyncio.create_task(cleanup_worker())

    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass



app = FastAPI(lifespan=lifespan)
app.include_router(ai.router, prefix="/ai", tags=["AI"])
app.include_router(admin_router)

# 注册自定义异常处理器：每种异常只注册一次
app.add_exception_handler(
    NotFoundError,
    not_found_exception_handler
)

app.add_exception_handler(
    PermissionDeniedError,
    permission_denied_exception_handler
)

app.add_exception_handler(
    BadRequestError,
    bad_request_exception_handler
)

app.add_exception_handler(
    UnauthorizedError,
    unauthorized_exception_handler
)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    try:
        response = await call_next(request)
    except Exception:
        process_time = time.time() - start_time

        logger.exception(
            "%s %s 请求发生未处理异常，耗时 %.3fs",
            request.method,
            request.url.path,
            process_time
        )
        raise

    process_time = time.time() - start_time

    logger.info(
        "%s %s %s %.3fs",
        request.method,
        request.url.path,
        response.status_code,
        process_time
    )

    return response


# 请求参数校验失败
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数校验失败",
            "data": None
        }
    )


# 注册路由
app.include_router(users_router)
app.include_router(articles_router)


@app.get("/")
def root():
    return {"message": "Hello World"}



    




