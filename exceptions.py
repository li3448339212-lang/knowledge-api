
from fastapi import Request
from fastapi.responses import JSONResponse


class NotFoundError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


class BadRequestError(Exception):
    pass


class UnauthorizedError(Exception):
    pass


async def not_found_exception_handler(
    request: Request,
    exc: NotFoundError
):
    return JSONResponse(
        status_code=404,
        content={
            "code": 404,
            "message": str(exc) or "资源不存在",
            "data": None
        }
    )


async def permission_denied_exception_handler(
    request: Request,
    exc: PermissionDeniedError
):
    return JSONResponse(
        status_code=403,
        content={
            "code": 403,
            "message": str(exc) or "没有权限执行此操作",
            "data": None
        }
    )


async def bad_request_exception_handler(
    request: Request,
    exc: BadRequestError
):
    return JSONResponse(
        status_code=400,
        content={
            "code": 400,
            "message": str(exc) or "请求参数不正确",
            "data": None
        }
    )


async def unauthorized_exception_handler(
    request: Request,
    exc: UnauthorizedError
):
    return JSONResponse(
        status_code=401,
        content={
            "code": 401,
            "message": str(exc) or "未授权，请先登录",
            "data": None
        },
        headers={"WWW-Authenticate": "Bearer"}
    )