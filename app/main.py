"""! @file main.py
 @brief Linux 存储管理 Web 面板路由层

 基于 FastAPI 实现 HTTP 接口与静态文件服务，包含：
 - HTTP Basic Auth 认证中间件
 - Pydantic 422 验证错误中文翻译
 - 业务函数调用与审计日志记录
 - 异常统一处理

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from src.database.core import Base, engine, SessionLocal
from src.database import crud
from src.schemas import (
    DeleteDirectoryRequest,
    DirectoryRequest,
    FilesystemRequest,
    LabelRequest,
    MountRequest,
    PermissionRequest,
    ResizeRequest,
    UnmountRequest,
)
from app.storage import (
    CommandError,
    create_directory,
    delete_directory,
    get_devices,
    get_mounts,
    get_usage,
    list_directory,
    make_filesystem,
    resize_filesystem,
    set_label,
    set_permissions,
    unmount_device,
    mount_device,
)


# FastAPI 应用实例
app = FastAPI(title="Linux 存储管理", version="1.0.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# 启动时创建所有数据库表
Base.metadata.create_all(bind=engine)

# 认证用户名与密码，可通过环境变量覆盖
AUTH_USER = os.getenv("STORAGE_MANAGER_USER", "admin")
AUTH_PASSWORD = os.getenv("STORAGE_MANAGER_PASSWORD", "change-me")


def authenticated(request: Request) -> bool:
    """! 校验请求是否通过 HTTP Basic Auth 认证

    使用 @c secrets.compare_digest 进行常量时间比较，防止时序攻击。

    @param request FastAPI 请求对象
    @return 认证通过返回 True，否则返回 False
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
    except Exception:
        return False
    username, _, password = decoded.partition(":")
    return secrets.compare_digest(username, AUTH_USER) and secrets.compare_digest(
        password, AUTH_PASSWORD
    )


@app.middleware("http")
async def require_basic_auth(request: Request, call_next):
    """! HTTP Basic Auth 认证中间件

    对除 @c /api/health 外的所有请求进行认证，未通过时返回 401 并携带
    @c WWW-Authenticate 响应头。

    @param request FastAPI 请求对象
    @param call_next 下一个中间件或路由处理函数
    @return 原响应或 401 认证响应
    """
    if request.url.path == "/api/health" or authenticated(request):
        return await call_next(request)
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Storage Manager"'},
        content="Authentication required",
    )


def _translate_validation_error(error: dict) -> dict:
    """! 将 Pydantic 验证错误翻译为中文

    根据 @c error["type"] 将英文错误类型映射为中文提示，保留原始类型信息。
    schemas.py 中 @c field_validator 设置的自定义中文错误直接透传。

    @param error Pydantic 单条错误字典
    @return 包含 field、message、type 的字典
    """
    error_type = error.get("type", "")
    msg = error.get("msg", "")
    loc = error.get("loc", [])

    # 常见 Pydantic 错误类型映射
    if error_type == "missing":
        msg = "此项为必填项，不能为空"
    elif error_type == "type_error.str":
        msg = "请输入有效的文本"
    elif error_type == "type_error.bool":
        msg = "请选择是或否"
    elif error_type == "type_error.integer":
        msg = "请输入有效的整数"
    elif error_type == "type_error.float":
        msg = "请输入有效的数字"
    elif error_type == "type_error.none.not_allowed":
        msg = "此项不能为空"
    elif "string_too_short" in error_type:
        limit = error.get("ctx", {}).get("min_length", "")
        msg = f"输入内容过短，至少需要 {limit} 个字符" if limit else "输入内容过短"
    elif "string_too_long" in error_type:
        limit = error.get("ctx", {}).get("max_length", "")
        msg = f"输入内容过长，最多允许 {limit} 个字符" if limit else "输入内容过长"
    elif error_type == "greater_than":
        limit = error.get("ctx", {}).get("gt", "")
        msg = f"输入值必须大于 {limit}" if limit else "输入值过小"
    elif error_type == "less_than":
        limit = error.get("ctx", {}).get("lt", "")
        msg = f"输入值必须小于 {limit}" if limit else "输入值过大"
    elif "greater_than_equal" in error_type:
        limit = error.get("ctx", {}).get("ge", "")
        msg = f"输入值必须大于等于 {limit}" if limit else "输入值过小"
    elif "less_than_equal" in error_type:
        limit = error.get("ctx", {}).get("le", "")
        msg = f"输入值必须小于等于 {limit}" if limit else "输入值过大"
    elif error_type == "int_from_float":
        msg = "请输入整数，不要包含小数"
    elif "value_error" in error_type:
        # schemas.py 中 field_validator 设置的自定义错误已经是中文，保留
        pass

    # 提取字段名（去掉 body/query 前缀）
    field_name = ""
    if len(loc) >= 2 and loc[0] in ("body", "query"):
        field_name = str(loc[1])
    elif len(loc) >= 1:
        field_name = str(loc[-1])

    return {"field": field_name, "message": msg, "type": error_type}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """! 处理 Pydantic 请求验证异常

    将错误列表逐条翻译为中文后，返回 422 统一响应结构。

    @param request FastAPI 请求对象
    @param exc RequestValidationError 异常实例
    @return 422 JSONResponse
    """
    errors = [_translate_validation_error(err) for err in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": errors, "message": "表单验证失败，请检查输入内容"},
    )


def _to_beijing(dt):
    """! 将 UTC 时间转换为北京时间（UTC+8）

    若时间对象无时区信息，则先按 UTC 处理，再转换为东八区时间。

    @param dt datetime 对象或空值
    @return 格式化后的北京时间字符串，空值返回空字符串
    """
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    """! 数据库会话依赖

    通过 FastAPI @c Depends 注入，每个请求独立获取一个 SQLAlchemy Session，
    请求结束后自动关闭。

    @yield SQLAlchemy Session 对象
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _log_action(
    db: Session, action: str, params: dict, result: dict[str, str]
) -> None:
    """! 统一记录审计日志

    将操作类型、参数、执行命令、返回码及输出写入数据库。stdout/stderr
    各保留末尾 4000 字符，避免日志过大。

    @param db SQLAlchemy Session
    @param action 操作类型标识
    @param params 请求参数字典
    @param result 命令执行结果字典
    """
    crud.create_audit_log(
        db,
        action=action,
        params=json.dumps(params, ensure_ascii=False),
        command=" ".join(result.get("command", [])),
        return_code=result.get("return_code", 0),
        stdout=result.get("stdout", "")[-4000:],
        stderr=result.get("stderr", "")[-4000:],
    )


@app.exception_handler(CommandError)
async def command_error_handler(_, exc: CommandError):
    """! 处理业务逻辑层命令执行异常

    将 @ref CommandError 转换为 400 Bad Request 响应，错误信息直接返回前端。

    @param _ 未使用的 request 参数
    @param exc CommandError 异常实例
    @return 400 JSONResponse
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/")
def index() -> FileResponse:
    """! 返回前端主页面

    @return index.html 文件响应
    """
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    """! 健康检查接口

    无需认证，用于负载均衡或服务探活。

    @return 状态字典 @c {"status": "ok"}
    """
    return {"status": "ok"}


@app.get("/api/devices")
def devices() -> dict:
    """! 获取块设备列表

    @return lsblk 解析后的设备信息字典
    """
    return get_devices()


@app.get("/api/mounts")
def mounts() -> dict:
    """! 获取挂载点列表

    @return findmnt 解析后的挂载信息字典
    """
    return get_mounts()


@app.get("/api/usage")
def usage() -> list[dict[str, str]]:
    """! 获取磁盘空间使用情况

    @return df 解析后的空间使用记录列表
    """
    return get_usage()


@app.post("/api/mount")
def mount(payload: MountRequest, db: Session = Depends(get_db)) -> dict:
    """! 挂载设备接口

    @param payload 挂载请求参数
    @param db 数据库会话依赖
    @return 命令执行结果
    """
    result = mount_device(payload)
    _log_action(db, "mount", payload.model_dump(), result)
    return result


@app.post("/api/unmount")
def unmount(payload: UnmountRequest, db: Session = Depends(get_db)) -> dict:
    """! 卸载设备接口

    @param payload 卸载请求参数
    @param db 数据库会话依赖
    @return 命令执行结果
    """
    result = unmount_device(payload)
    _log_action(db, "unmount", payload.model_dump(), result)
    return result


@app.post("/api/filesystems")
def filesystem(payload: FilesystemRequest, db: Session = Depends(get_db)) -> dict:
    """! 创建文件系统（格式化）接口

    @param payload 格式化请求参数
    @param db 数据库会话依赖
    @return 命令执行结果
    """
    result = make_filesystem(payload)
    _log_action(db, "make_filesystem", payload.model_dump(), result)
    return result


@app.post("/api/resize")
def resize(payload: ResizeRequest, db: Session = Depends(get_db)) -> dict:
    """! 扩展文件系统接口

    @param payload 扩容请求参数
    @param db 数据库会话依赖
    @return 命令执行结果
    """
    result = resize_filesystem(payload)
    _log_action(db, "resize_filesystem", payload.model_dump(), result)
    return result


@app.post("/api/label")
def label(payload: LabelRequest, db: Session = Depends(get_db)) -> dict:
    """! 修改文件系统卷标接口

    @param payload 卷标修改请求参数
    @param db 数据库会话依赖
    @return 命令执行结果
    """
    result = set_label(payload)
    _log_action(db, "set_label", payload.model_dump(), result)
    return result


@app.get("/api/directories")
def directories(path: str = Query("/mnt")) -> list[dict]:
    """! 列出目录内容接口

    @param path 目标目录路径，默认为 @c /mnt
    @return 目录条目列表
    @raises HTTPException 当路径无效或读取失败时抛出 400 错误
    """
    try:
        return list_directory(path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/directories")
def create_dir(payload: DirectoryRequest, db: Session = Depends(get_db)) -> dict:
    """! 创建目录接口

    @param payload 目录创建请求参数
    @param db 数据库会话依赖
    @return 创建结果
    """
    result = create_directory(payload)
    crud.create_audit_log(
        db,
        action="create_directory",
        params=json.dumps(payload.model_dump(), ensure_ascii=False),
        command=" ".join(result.get("command", [])),
        return_code=0,
        stdout="",
        stderr="",
    )
    return result


@app.delete("/api/directories")
def delete_dir(payload: DeleteDirectoryRequest, db: Session = Depends(get_db)) -> dict:
    """! 删除目录接口

    @param payload 目录删除请求参数
    @param db 数据库会话依赖
    @return 删除结果
    """
    result = delete_directory(payload)
    crud.create_audit_log(
        db,
        action="delete_directory",
        params=json.dumps(payload.model_dump(), ensure_ascii=False),
        command=" ".join(result.get("command", [])),
        return_code=0,
        stdout="",
        stderr="",
    )
    return result


@app.post("/api/permissions")
def permissions(payload: PermissionRequest, db: Session = Depends(get_db)) -> dict:
    """! 设置权限接口

    @param payload 权限请求参数
    @param db 数据库会话依赖
    @return 权限设置结果
    """
    result = set_permissions(payload)
    crud.create_audit_log(
        db,
        action="set_permissions",
        params=json.dumps(payload.model_dump(), ensure_ascii=False),
        command=" ".join(result.get("command", [])),
        return_code=0,
        stdout="",
        stderr="",
    )
    return result


@app.get("/api/audit")
def audit(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)) -> list[dict]:
    """! 查询审计日志接口

    按时间倒序返回最近的操作记录，并将 UTC 时间转换为北京时间展示。

    @param limit 返回记录数量上限，范围 [1, 500]，默认 100
    @param db 数据库会话依赖
    @return 审计日志记录列表
    """
    logs = crud.get_audit_logs(db, limit=limit)
    return [
        {
            "id": log.id,
            "action": log.action,
            "params": log.params,
            "command": log.command,
            "return_code": log.return_code,
            "stdout": log.stdout,
            "stderr": log.stderr,
            "created_at": _to_beijing(log.created_at),
        }
        for log in logs
    ]
