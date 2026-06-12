"""! @file test_storage.py
 @brief 业务逻辑层单元测试

 对 @c app.storage 模块中的核心函数进行单元测试，覆盖异常类属性、
 关键目录保护、Pydantic 模型校验、磁盘空间查询和目录列表等功能。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

import pytest

from app.storage import CommandError, ensure_not_critical, get_usage, list_directory
from src.schemas import (
    DirectoryRequest,
    FilesystemRequest,
    MountRequest,
    PermissionRequest,
    ResizeRequest,
    UnmountRequest,
)


class TestCommandError:
    """! CommandError 异常类测试"""

    def test_command_error_attributes(self) -> None:
        """! 验证 CommandError 携带的属性"""
        exc = CommandError("test error", 2, ["cmd", "arg"], "stdout", "stderr")
        assert exc.return_code == 2
        assert exc.command == ["cmd", "arg"]
        assert exc.stdout == "stdout"
        assert exc.stderr == "stderr"
        assert str(exc) == "test error"


class TestEnsureNotCritical:
    """! 关键目录保护测试"""

    def test_safe_path(self) -> None:
        """! 安全路径应正常通过"""
        path = ensure_not_critical("/mnt/data")
        assert str(path) == "/mnt/data"

    def test_safe_under_root(self) -> None:
        """! / 下的非关键目录（如 /mnt /home）应允许操作"""
        path = ensure_not_critical("/home/user")
        assert str(path) == "/home/user"

    def test_critical_path(self) -> None:
        """! 根目录应被保护"""
        with pytest.raises(CommandError):
            ensure_not_critical("/")

    def test_critical_path_bin(self) -> None:
        """! /bin 应被保护"""
        with pytest.raises(CommandError):
            ensure_not_critical("/bin")

    def test_critical_subdirectory(self) -> None:
        """! 在关键目录下创建/删除子目录也应被禁止"""
        with pytest.raises(CommandError):
            ensure_not_critical("/etc/nginx")
        with pytest.raises(CommandError):
            ensure_not_critical("/var/log/test")
        with pytest.raises(CommandError):
            ensure_not_critical("/usr/local/bin")


class TestSchemas:
    """! Pydantic 模型校验测试"""

    def test_mount_request_valid(self) -> None:
        """! 合法挂载请求应正常创建"""
        req = MountRequest(device="/dev/sdb1", mount_point="/mnt/data")
        assert req.device == "/dev/sdb1"
        assert req.mount_point == "/mnt/data"

    def test_mount_request_invalid_device(self) -> None:
        """! 非法设备路径应抛出 ValueError"""
        with pytest.raises(ValueError):
            MountRequest(device="invalid", mount_point="/mnt/data")

    def test_mount_request_invalid_mount_point(self) -> None:
        """! 相对挂载点路径应抛出 ValueError"""
        with pytest.raises(ValueError):
            MountRequest(device="/dev/sdb1", mount_point="relative")

    def test_mount_request_invalid_fs_type(self) -> None:
        """! 不支持的文件系统类型应抛出 ValueError"""
        with pytest.raises(ValueError):
            MountRequest(device="/dev/sdb1", mount_point="/mnt/data", fs_type="ntfs")

    def test_unmount_request_valid(self) -> None:
        """! 合法卸载请求应正常创建"""
        req = UnmountRequest(target="/mnt/data")
        assert req.target == "/mnt/data"
        assert req.force is False

    def test_filesystem_request_valid(self) -> None:
        """! 合法格式化请求应正常创建"""
        req = FilesystemRequest(device="/dev/sdb1", fs_type="ext4")
        assert req.fs_type == "ext4"

    def test_filesystem_request_invalid_type(self) -> None:
        """! 不支持的文件系统类型应抛出 ValueError"""
        with pytest.raises(ValueError):
            FilesystemRequest(device="/dev/sdb1", fs_type="zfs")

    def test_resize_request_valid(self) -> None:
        """! 合法扩容请求应正常创建"""
        req = ResizeRequest(device="/dev/sdb1", fs_type="ext4")
        assert req.device == "/dev/sdb1"

    def test_permission_request_valid(self) -> None:
        """! 合法权限请求应正常创建"""
        req = PermissionRequest(path="/tmp", mode="755")
        assert req.mode == "755"
        assert req.owner is None

    def test_permission_request_invalid_mode(self) -> None:
        """! 非法权限模式应抛出 ValueError"""
        with pytest.raises(ValueError):
            PermissionRequest(path="/tmp", mode="abc")

    def test_permission_request_nonexistent_owner(self) -> None:
        """! 不存在的属主用户应抛出 ValueError"""
        with pytest.raises(ValueError):
            PermissionRequest(path="/tmp", mode="755", owner="nonexistent_user_xyz")

    def test_directory_request_valid(self) -> None:
        """! 合法目录请求应正常创建"""
        req = DirectoryRequest(path="/tmp/test_dir")
        assert req.path == "/tmp/test_dir"

    def test_directory_request_invalid_path(self) -> None:
        """! 相对路径应抛出 ValueError"""
        with pytest.raises(ValueError):
            DirectoryRequest(path="relative")


class TestGetUsage:
    """! 磁盘空间查询测试"""

    def test_returns_list(self) -> None:
        """! get_usage 应返回列表"""
        result = get_usage()
        assert isinstance(result, list)
        if result:
            assert "filesystem" in result[0]
            assert "type" in result[0]


class TestListDirectory:
    """! 目录列表测试"""

    def test_list_tmp(self) -> None:
        """! 列出 /tmp 目录应返回列表"""
        result = list_directory("/tmp")
        assert isinstance(result, list)

    def test_invalid_path(self) -> None:
        """! 相对路径应抛出 ValueError"""
        with pytest.raises(ValueError):
            list_directory("relative")
