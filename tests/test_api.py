"""! @file test_api.py
 @brief FastAPI 接口集成测试

 使用 FastAPI TestClient 对路由层进行集成测试，覆盖认证、只读接口、
 参数校验等场景。测试使用内存 SQLite 覆盖 @c get_db 依赖。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

import base64
import os

# 在导入 app.main 前设置测试环境变量，使认证配置生效
os.environ["STORAGE_MANAGER_USER"] = "admin"
os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"

from fastapi.testclient import TestClient  # noqa: E402
from http import HTTPStatus  # noqa: E402

from app.main import app, get_db  # noqa: E402
from tests.mock_db import TestingSessionLocal  # noqa: E402


def override_get_db():
    """! 测试用数据库依赖覆盖

    使用内存 SQLite 会话替换原 get_db，确保测试互不干扰。

    @yield SQLAlchemy Session 对象
    """
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def _auth_header(user: str = "admin", password: str = "admin") -> dict[str, str]:
    """! 生成 HTTP Basic Auth 请求头

    @param user 用户名，默认 admin
    @param password 密码，默认 admin
    @return 包含 Authorization 的请求头字典
    """
    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


class TestAuth:
    """! 认证相关测试"""

    def test_health_no_auth(self) -> None:
        """! 健康检查接口无需认证"""
        response = client.get("/api/health")
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"status": "ok"}

    def test_index_requires_auth(self) -> None:
        """! 首页访问需要认证"""
        response = client.get("/")
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_index_with_auth(self) -> None:
        """! 携带正确认证信息可访问首页"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/", headers=_auth_header())
        assert response.status_code == HTTPStatus.OK

    def test_invalid_auth(self) -> None:
        """! 非法认证信息应返回 401"""
        response = client.get("/", headers={"Authorization": "Basic invalid"})
        assert response.status_code == HTTPStatus.UNAUTHORIZED


class TestDevicesAndUsage:
    """! 设备与空间信息接口测试"""

    def test_get_devices(self) -> None:
        """! 获取块设备列表"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/api/devices", headers=_auth_header())
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert "blockdevices" in data or data == {}

    def test_get_usage(self) -> None:
        """! 获取磁盘空间使用情况"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/api/usage", headers=_auth_header())
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_mounts(self) -> None:
        """! 获取挂载点信息"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/api/mounts", headers=_auth_header())
        assert response.status_code == HTTPStatus.OK


class TestDirectories:
    """! 目录接口测试"""

    def test_list_directories(self) -> None:
        """! 列出目录内容"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/api/directories?path=/tmp", headers=_auth_header())
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert isinstance(data, list)

    def test_list_directories_invalid_path(self) -> None:
        """! 相对路径应返回 400"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/api/directories?path=relative", headers=_auth_header())
        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestAuditLogs:
    """! 审计日志接口测试"""

    def test_get_audit_empty(self) -> None:
        """! 查询审计日志返回列表"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.get("/api/audit?limit=10", headers=_auth_header())
        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert isinstance(data, list)


class TestValidation:
    """! 请求参数校验测试"""

    def test_mount_invalid_device(self) -> None:
        """! 非法设备路径应返回 422"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.post(
            "/api/mount",
            json={"device": "invalid", "mount_point": "/mnt/test"},
            headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_mount_invalid_mount_point(self) -> None:
        """! 非法挂载点路径应返回 422"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.post(
            "/api/mount",
            json={"device": "/dev/sdb1", "mount_point": "relative"},
            headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_filesystem_invalid_type(self) -> None:
        """! 不支持的文件系统类型应返回 422"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.post(
            "/api/filesystems",
            json={"device": "/dev/sdb1", "fs_type": "ntfs"},
            headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_permission_invalid_mode(self) -> None:
        """! 非法权限模式应返回 422"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.post(
            "/api/permissions",
            json={"path": "/tmp", "mode": "invalid"},
            headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_permission_nonexistent_owner(self) -> None:
        """! 不存在的属主用户应返回 422"""
        os.environ["STORAGE_MANAGER_PASSWORD"] = "admin"
        response = client.post(
            "/api/permissions",
            json={"path": "/tmp", "mode": "755", "owner": "nonexistent_user_12345"},
            headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()},
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
