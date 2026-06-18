"""! @file schemas.py
 @brief Pydantic 请求/响应数据模型

 定义所有 API 接口的输入校验模型，包括挂载、卸载、格式化、扩容、
 目录管理、权限设置和卷标修改等请求的数据结构与校验规则。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from __future__ import annotations

import grp
import pwd
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


# 合法设备路径正则：必须以 /dev/ 开头，后续为允许的字符
DEVICE_RE = re.compile(r"^/dev/[A-Za-z0-9_./+-]+$")

# 权限模式正则：3 或 4 位八进制数字
MODE_RE = re.compile(r"^[0-7]{3,4}$")

# 支持的文件系统类型集合
SAFE_FS_TYPES = {"ext4", "ext3", "ext2", "xfs", "btrfs"}


class MountRequest(BaseModel):
    """! 挂载设备请求模型

    @param device 设备路径，必须位于 /dev 下
    @param mount_point 挂载点绝对路径
    @param fs_type 文件系统类型，可选
    @param options 挂载参数选项，可选，最长 160 字符
    """

    device: str
    mount_point: str
    fs_type: str | None = None
    options: str | None = Field(default=None, max_length=160)

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        """! 校验设备路径格式

        @param value 输入的设备路径
        @return 校验通过的设备路径
        @raises ValueError 当路径不符合 /dev 下设备格式时抛出
        """
        if not DEVICE_RE.fullmatch(value):
            raise ValueError("设备路径必须位于 /dev 下")
        return value

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, value: str) -> str:
        """! 校验挂载点为绝对路径

        @param value 输入的挂载点路径
        @return 规范化后的绝对路径
        @raises ValueError 当路径不是绝对路径时抛出
        """
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("路径必须为绝对路径")
        return str(path)

    @field_validator("fs_type")
    @classmethod
    def validate_fs_type(cls, value: str | None) -> str | None:
        """! 校验文件系统类型

        @param value 输入的文件系统类型
        @return 校验通过的类型或 None
        @raises ValueError 当类型不在支持列表中时抛出
        """
        if value is None or value == "":
            return None
        if value not in SAFE_FS_TYPES:
            raise ValueError(f"仅支持文件系统类型: {', '.join(sorted(SAFE_FS_TYPES))}")
        return value

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: str | None) -> str | None:
        """! 校验挂载参数字符集

        @param value 输入的挂载选项字符串
        @return 校验通过的选项字符串或 None
        @raises ValueError 当包含非法字符时抛出
        """
        if not value:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_,.=:-]+", value):
            raise ValueError(
                "挂载参数只能包含字母、数字、下划线、逗号、点、等号、冒号和短横线"
            )
        return value


class UnmountRequest(BaseModel):
    """! 卸载设备请求模型

    @param target 设备路径或挂载点路径
    @param force 是否强制卸载，默认 False
    """

    target: str
    force: bool = False

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        """! 校验卸载目标

        目标可以是 /dev 下的设备路径，也可以是绝对路径形式的挂载点。

        @param value 输入的卸载目标
        @return 校验通过的目标路径
        @raises ValueError 当格式不合法时抛出
        """
        if value.startswith("/dev/"):
            if not DEVICE_RE.fullmatch(value):
                raise ValueError("设备路径必须位于 /dev 下")
            return value
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("路径必须为绝对路径")
        return str(path)


class FilesystemRequest(BaseModel):
    """! 创建文件系统（格式化）请求模型

    @param device 待格式化的设备路径
    @param fs_type 目标文件系统类型
    @param label 卷标，可选，最长 32 字符
    @param force 是否强制格式化，默认 False
    """

    device: str
    fs_type: str
    label: str | None = Field(default=None, max_length=32)
    force: bool = False

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        """! 校验待格式化设备路径

        @param value 输入的设备路径
        @return 校验通过的设备路径
        @raises ValueError 当路径不符合 /dev 下设备格式时抛出
        """
        if not DEVICE_RE.fullmatch(value):
            raise ValueError("设备路径必须位于 /dev 下")
        return value

    @field_validator("fs_type")
    @classmethod
    def validate_fs_type(cls, value: str) -> str:
        """! 校验文件系统类型

        @param value 输入的文件系统类型
        @return 校验通过的文件系统类型
        @raises ValueError 当类型不支持时抛出
        """
        if value not in SAFE_FS_TYPES:
            raise ValueError(f"仅支持文件系统类型: {', '.join(sorted(SAFE_FS_TYPES))}")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        """! 校验卷标格式

        @param value 输入的卷标
        @return 校验通过的卷标或 None
        @raises ValueError 当卷标包含非法字符时抛出
        """
        if value is None or value == "":
            return None
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("卷标只能包含字母、数字、下划线、点和短横线")
        return value


class ResizeRequest(BaseModel):
    """! 扩展文件系统请求模型

    @param device 设备路径
    @param fs_type 文件系统类型
    @param mount_point 挂载点，xfs/btrfs 扩容时必填
    """

    device: str
    fs_type: str
    mount_point: str | None = None

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        """! 校验扩容设备路径

        @param value 输入的设备路径
        @return 校验通过的设备路径
        @raises ValueError 当路径不符合 /dev 下设备格式时抛出
        """
        if not DEVICE_RE.fullmatch(value):
            raise ValueError("设备路径必须位于 /dev 下")
        return value

    @field_validator("fs_type")
    @classmethod
    def validate_fs_type(cls, value: str) -> str:
        """! 校验扩容支持的文件系统类型

        @param value 输入的文件系统类型
        @return 校验通过的文件系统类型
        @raises ValueError 当类型不支持时抛出
        """
        if value not in {"ext4", "ext3", "ext2", "xfs", "btrfs"}:
            raise ValueError("仅支持 ext、xfs、btrfs 扩容")
        return value

    @field_validator("mount_point")
    @classmethod
    def validate_mount_point(cls, value: str | None) -> str | None:
        """! 校验挂载点路径

        @param value 输入的挂载点路径
        @return 规范化后的绝对路径或 None
        @raises ValueError 当路径不是绝对路径时抛出
        """
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("路径必须为绝对路径")
        return str(path)


class DirectoryRequest(BaseModel):
    """! 目录操作基础请求模型

    @param path 目录绝对路径
    """

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """! 校验目录路径为绝对路径

        @param value 输入的路径
        @return 规范化后的绝对路径
        @raises ValueError 当路径不是绝对路径时抛出
        """
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("路径必须为绝对路径")
        return str(path)


class DeleteDirectoryRequest(DirectoryRequest):
    """! 删除目录请求模型

    @param path 待删除目录的绝对路径
    @param recursive 是否递归删除，默认 False
    """

    recursive: bool = False


class LabelRequest(BaseModel):
    """! 修改文件系统卷标请求模型

    @param device 设备路径
    @param fs_type 文件系统类型
    @param label 新卷标，最长 32 字符
    """

    device: str
    fs_type: str
    label: str = Field(..., max_length=32)

    @field_validator("device")
    @classmethod
    def validate_device(cls, value: str) -> str:
        """! 校验卷标修改目标设备路径

        @param value 输入的设备路径
        @return 校验通过的设备路径
        @raises ValueError 当路径不符合 /dev 下设备格式时抛出
        """
        if not DEVICE_RE.fullmatch(value):
            raise ValueError("设备路径必须位于 /dev 下")
        return value

    @field_validator("fs_type")
    @classmethod
    def validate_fs_type(cls, value: str) -> str:
        """! 校验卷标修改支持的文件系统类型

        @param value 输入的文件系统类型
        @return 校验通过的文件系统类型
        @raises ValueError 当类型不支持时抛出
        """
        if value not in SAFE_FS_TYPES:
            raise ValueError(f"仅支持文件系统类型: {', '.join(sorted(SAFE_FS_TYPES))}")
        return value

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        """! 校验新卷标格式

        @param value 输入的卷标
        @return 校验通过的卷标
        @raises ValueError 当卷标包含非法字符时抛出
        """
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("卷标只能包含字母、数字、下划线、点和短横线")
        return value


class PermissionRequest(DirectoryRequest):
    """! 设置权限请求模型

    @param path 目标路径
    @param mode 八进制权限模式，如 755 或 0755
    @param owner 新属主用户名，可选
    @param group 新属组名，可选
    """

    mode: str
    owner: str | None = None
    group: str | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        """! 校验权限模式格式

        @param value 输入的权限字符串
        @return 校验通过的权限字符串
        @raises ValueError 当格式不是 3-4 位八进制数时抛出
        """
        if not MODE_RE.fullmatch(value):
            raise ValueError("权限格式应为 755 或 0755")
        return value

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value: str | None) -> str | None:
        """! 校验属主用户存在性

        @param value 输入的用户名
        @return 校验通过的用户名或 None
        @raises ValueError 当用户不存在于系统时抛出
        """
        if not value:
            return None
        try:
            pwd.getpwnam(value)
        except KeyError as exc:
            raise ValueError(f"用户不存在: {value}") from exc
        return value

    @field_validator("group")
    @classmethod
    def validate_group(cls, value: str | None) -> str | None:
        """! 校验属组存在性

        @param value 输入的用户组名
        @return 校验通过的组名或 None
        @raises ValueError 当用户组不存在于系统时抛出
        """
        if not value:
            return None
        try:
            grp.getgrnam(value)
        except KeyError as exc:
            raise ValueError(f"用户组不存在: {value}") from exc
        return value
