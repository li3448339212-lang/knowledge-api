
import time

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

from logger import logger


app = FastAPI()


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



    




