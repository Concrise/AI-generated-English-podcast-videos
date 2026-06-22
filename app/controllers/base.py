import secrets
from uuid import uuid4

from fastapi import Request

from app.config import config
from app.models.exception import HttpException


def get_task_id(request: Request):
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = uuid4()
    return str(task_id)


def get_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    return api_key


def verify_token(request: Request):
    if not config.app.get("auth_enabled", False):
        return

    expected_token = config.app.get("api_key", "")
    token = get_api_key(request) or ""
    if not expected_token or not secrets.compare_digest(token, expected_token):
        request_id = get_task_id(request)
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message="invalid api token",
        )
