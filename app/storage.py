"""! @file storage.py
 @brief Linux 存储管理业务逻辑层

 封装系统命令调用（mount/umount/mkfs/resize2fs 等），提供目录管理、
 权限设置、文件系统卷标修改等操作，并包含关键系统目录保护逻辑。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import shutil
import subprocess
from pathlib import Path
from typing import Any

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


# 关键系统目录集合，禁止对其进行创建/删除/权限修改等写操作
CRITICAL_PATHS = {
    Path("/"),
    Path("/bin"),
    Path("/boot"),
    Path("/dev"),
    Path("/etc"),
    Path("/lib"),
    Path("/lib64"),
    Path("/proc"),
    Path("/root"),
    Path("/run"),
    Path("/sbin"),
    Path("/sys"),
    Path("/usr"),
    Path("/var"),
}


class CommandError(RuntimeError):
    """! 命令执行异常

    携带命令执行的返回码、命令本身以及标准输出/错误输出，便于路由层
    统一处理错误响应和审计日志记录。

    @extends RuntimeError
    """

    def __init__(
        self,
        message: str,
        return_code: int = 1,
        command: list[str] | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """! 构造命令执行异常

        @param message 错误描述信息
        @param return_code 命令返回码，默认为 1
        @param command 执行的命令参数列表
        @param stdout 命令标准输出内容
        @param stderr 命令标准错误内容
        """
        super().__init__(message)
        self.return_code = return_code
        self.command = command or []
        self.stdout = stdout
        self.stderr = stderr


def ensure_not_critical(path: str | Path) -> Path:
    """! 校验路径不在关键系统目录保护范围内

    对输入路径进行展开（expanduser）和解析（resolve），并与关键系统目录
    集合及其符号链接解析后的真实路径进行比对。若路径本身是关键目录，
    或位于某个非根关键目录之下，则抛出 @ref CommandError。

    @param path 待校验的文件系统路径
    @return 解析后的 Path 对象
    @raises CommandError 当路径属于关键系统目录时抛出

    @note 根目录 @c / 不用于子目录判断，否则 /mnt、/home 等常规路径也会被误禁。
    """
    path = Path(path).expanduser().resolve()

    # 收集所有关键路径（原始 + 解析符号链接后），去重
    critical_set = set(CRITICAL_PATHS)
    for cp in list(CRITICAL_PATHS):
        critical_set.add(cp.resolve())

    # 1. 路径本身是关键目录
    if path in critical_set:
        raise CommandError(f"拒绝操作关键系统目录: {path}")

    # 2. 路径在某个非根关键目录下（/ 除外，否则 /mnt /home 等合法路径也会被禁）
    for critical in critical_set:
        if critical == Path("/"):
            continue
        try:
            path.relative_to(critical)
            raise CommandError(f"拒绝操作关键系统目录: {path}")
        except ValueError:
            pass

    return path


def run_command(action: str, params: dict[str, Any], command: list[str]) -> dict[str, Any]:
    """! 执行系统命令并返回完整结果

    在执行前检查命令是否存在，执行后根据返回码决定是否抛出异常。
    本函数不内嵌审计日志记录，由调用方（路由层）统一处理。

    @param action 操作类型标识，用于错误信息
    @param params 请求参数字典，用于错误信息
    @param command 待执行的命令参数列表
    @return 包含 command、stdout、stderr、return_code 的字典
    @raises CommandError 当命令不存在或执行失败时抛出
    """
    if not command:
        raise CommandError("命令为空")
    if shutil.which(command[0]) is None:
        raise CommandError(f"命令不存在: {command[0]}", 127)
    proc = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    result = {
        "command": command,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "return_code": proc.returncode,
    }
    if proc.returncode != 0:
        raise CommandError(
            proc.stderr.strip() or proc.stdout.strip() or "命令执行失败",
            proc.returncode,
            command,
            proc.stdout,
            proc.stderr,
        )
    return result


def read_json_command(command: list[str]) -> Any:
    """! 执行命令并将 JSON 标准输出解析为 Python 对象

    适用于 @c lsblk --json、@c findmnt --json 等返回 JSON 的系统工具。

    @param command 待执行的命令参数列表
    @return 解析后的 JSON 对象；若命令不存在、执行失败或解析失败则返回空字典
    """
    if shutil.which(command[0]) is None:
        return {}
    proc = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def get_devices() -> dict[str, Any]:
    """! 获取系统块设备信息

    通过 @c lsblk --json -O 获取所有块设备及其层级关系的 JSON 数据。

    @return 包含 @c blockdevices 等字段的字典
    """
    return read_json_command(["lsblk", "--json", "-O"])


def get_mounts() -> dict[str, Any]:
    """! 获取系统挂载点信息

    通过 @c findmnt --json --real 获取真实文件系统的挂载信息。

    @return 包含挂载目标、源设备、文件系统类型等字段的字典
    """
    return read_json_command(
        ["findmnt", "--json", "--real", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS,SIZE,USED,AVAIL,USE%"]
    )


def get_usage() -> list[dict[str, str]]:
    """! 获取磁盘空间使用情况

    解析 @c df -hT 的输出，将每行转换为包含文件系统、类型、容量、
    已用、可用、使用率、挂载点等字段的字典。

    @return 磁盘空间使用记录列表
    """
    proc = subprocess.run(
        ["df", "-hT"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return []
    lines = proc.stdout.strip().splitlines()
    if len(lines) < 2:
        return []
    rows = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        rows.append(
            {
                "filesystem": parts[0],
                "type": parts[1],
                "size": parts[2],
                "used": parts[3],
                "available": parts[4],
                "use_percent": parts[5],
                "mounted_on": parts[6],
            }
        )
    return rows


def mount_device(payload: MountRequest) -> dict[str, Any]:
    """! 挂载存储设备

    自动创建挂载点目录后，根据请求参数调用 @c mount 命令完成挂载。

    @param payload 挂载请求参数
    @return 命令执行结果字典
    @raises CommandError 当命令执行失败时抛出
    """
    mount_path = Path(payload.mount_point)
    mount_path.mkdir(parents=True, exist_ok=True)
    command = ["mount"]
    if payload.fs_type:
        command.extend(["-t", payload.fs_type])
    if payload.options:
        command.extend(["-o", payload.options])
    command.extend([payload.device, payload.mount_point])
    return run_command("mount", payload.model_dump(), command)


def unmount_device(payload: UnmountRequest) -> dict[str, Any]:
    """! 卸载存储设备或挂载点

    根据请求参数调用 @c umount 命令，支持强制卸载（@c -f）。

    @param payload 卸载请求参数
    @return 命令执行结果字典
    @raises CommandError 当命令执行失败时抛出
    """
    command = ["umount"]
    if payload.force:
        command.append("-f")
    command.append(payload.target)
    return run_command("unmount", payload.model_dump(), command)


def make_filesystem(payload: FilesystemRequest) -> dict[str, Any]:
    """! 创建文件系统（格式化）

    根据文件系统类型调用对应的 @c mkfs.* 工具，支持强制格式化与卷标设置。

    @param payload 格式化请求参数
    @return 命令执行结果字典
    @raises CommandError 当命令执行失败或文件系统类型不支持时抛出
    """
    command = [f"mkfs.{payload.fs_type}"]
    if payload.fs_type.startswith("ext") and payload.force:
        command.append("-F")
    elif payload.fs_type in {"xfs", "btrfs"} and payload.force:
        command.append("-f")
    if payload.label:
        command.extend(["-L", payload.label])
    command.append(payload.device)
    return run_command("make_filesystem", payload.model_dump(), command)


def resize_filesystem(payload: ResizeRequest) -> dict[str, Any]:
    """! 扩展文件系统空间

    根据文件系统类型选择扩容工具：
    - ext 系列：@c resize2fs 设备路径
    - xfs：@c xfs_growfs 挂载点
    - btrfs：@c btrfs filesystem resize max 挂载点

    @param payload 扩容请求参数
    @return 命令执行结果字典
    @raises CommandError 当缺少挂载点或命令执行失败时抛出
    """
    if payload.fs_type.startswith("ext"):
        command = ["resize2fs", payload.device]
    elif payload.fs_type == "xfs":
        if not payload.mount_point:
            raise CommandError("xfs 扩容需要提供挂载点")
        command = ["xfs_growfs", payload.mount_point]
    elif payload.fs_type == "btrfs":
        if not payload.mount_point:
            raise CommandError("btrfs 扩容需要提供挂载点")
        command = ["btrfs", "filesystem", "resize", "max", payload.mount_point]
    else:
        raise CommandError("不支持的文件系统类型")
    return run_command("resize_filesystem", payload.model_dump(), command)


def set_label(payload: LabelRequest) -> dict[str, Any]:
    """! 修改文件系统卷标

    根据文件系统类型选择对应的卷标修改工具：
    - ext 系列：@c e2label
    - xfs：@c xfs_admin -L
    - btrfs：@c btrfs filesystem label

    @param payload 卷标修改请求参数
    @return 命令执行结果字典
    @raises CommandError 当文件系统类型不支持或命令执行失败时抛出
    """
    if payload.fs_type.startswith("ext"):
        command = ["e2label", payload.device, payload.label]
    elif payload.fs_type == "xfs":
        command = ["xfs_admin", "-L", payload.label, payload.device]
    elif payload.fs_type == "btrfs":
        command = ["btrfs", "filesystem", "label", payload.device, payload.label]
    else:
        raise CommandError("不支持的文件系统类型")
    return run_command("set_label", payload.model_dump(), command)


def create_directory(payload: DirectoryRequest) -> dict[str, Any]:
    """! 创建目录

    先通过 @ref ensure_not_critical 校验路径安全性，若目录已存在则
    抛出异常避免覆盖。支持自动创建父目录（等价于 @c mkdir -p）。

    @param payload 目录创建请求参数
    @return 包含创建路径和命令信息的字典
    @raises CommandError 当路径受保护、目录已存在或创建失败时抛出
    """
    path = ensure_not_critical(payload.path)
    if path.exists():
        raise CommandError(f"目录已存在: {path}")
    try:
        path.mkdir(parents=True, exist_ok=False)
    except PermissionError:
        raise CommandError(f"没有权限创建目录: {path}")
    except OSError as exc:
        raise CommandError(f"创建目录失败: {exc}")
    return {"path": str(path), "created": True, "command": ["mkdir", "-p", str(path)]}


def delete_directory(payload: DeleteDirectoryRequest) -> dict[str, Any]:
    """! 删除目录

    支持递归删除（@c rm -r）和非空删除失败（@c rmdir）。
    先通过 @ref ensure_not_critical 校验路径安全性。

    @param payload 目录删除请求参数
    @return 包含删除路径和命令信息的字典
    @raises CommandError 当路径受保护、目录不存在或删除失败时抛出
    """
    path = ensure_not_critical(payload.path)
    if not path.exists():
        raise CommandError(f"目录不存在: {path}")
    if not path.is_dir():
        raise CommandError(f"不是目录: {path}")
    try:
        if payload.recursive:
            shutil.rmtree(path)
            command = ["rm", "-r", str(path)]
        else:
            path.rmdir()
            command = ["rmdir", str(path)]
    except PermissionError:
        raise CommandError(f"没有权限删除目录: {path}")
    except OSError as exc:
        raise CommandError(f"删除目录失败: {exc}")
    return {"path": str(path), "deleted": True, "command": command}


def set_permissions(payload: PermissionRequest) -> dict[str, Any]:
    """! 设置文件或目录权限及属主

    通过 @c os.chmod 修改权限，若指定了属主或属组，则通过
    @c pwd.getpwnam / @c grp.getgrnam 解析后调用 @c os.chown。

    @param payload 权限请求参数
    @return 包含修改路径、权限、属主和命令信息的字典
    @raises CommandError 当路径受保护、用户/组不存在或修改失败时抛出
    """
    path = ensure_not_critical(payload.path)
    if not path.exists():
        raise CommandError(f"路径不存在: {path}")
    try:
        os.chmod(path, int(payload.mode, 8))
        if payload.owner or payload.group:
            try:
                uid = -1 if not payload.owner else pwd.getpwnam(payload.owner).pw_uid
                gid = -1 if not payload.group else grp.getgrnam(payload.group).gr_gid
            except KeyError as exc:
                raise CommandError(f"用户或用户组不存在: {exc}")
            os.chown(path, uid, gid)
    except PermissionError:
        raise CommandError(f"没有权限修改该路径的权限: {path}")
    except OSError as exc:
        raise CommandError(f"修改权限失败: {exc}")
    return {
        "path": str(path),
        "mode": payload.mode,
        "owner": payload.owner,
        "group": payload.group,
        "command": ["chmod", payload.mode, str(path)],
    }


def list_directory(path: str) -> list[dict[str, Any]]:
    """! 列出指定目录下的文件和子目录

    返回结果按目录在前、文件在后排序，同类型按名称字典序排列。
    对无法解析 UID/GID 的情况，回退显示为用户/组 ID 数字。

    @param path 待列出的目录路径，必须为绝对路径
    @return 目录条目列表，每个条目包含名称、路径、是否目录、权限、属主、属组、大小
    @raises ValueError 当路径不是绝对路径时抛出
    @raises CommandError 当目录不存在、无权限或读取失败时抛出
    """
    root = Path(path).expanduser()
    if not root.is_absolute():
        raise ValueError("路径必须为绝对路径")
    try:
        entries = []
        for entry in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            try:
                stat = entry.stat()
            except (OSError, FileNotFoundError):
                continue
            try:
                owner = pwd.getpwuid(stat.st_uid).pw_name
            except KeyError:
                owner = str(stat.st_uid)
            try:
                group = grp.getgrgid(stat.st_gid).gr_name
            except KeyError:
                group = str(stat.st_gid)
            entries.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                    "mode": oct(stat.st_mode & 0o777),
                    "owner": owner,
                    "group": group,
                    "size": stat.st_size,
                }
            )
        return entries
    except FileNotFoundError:
        raise CommandError(f"目录不存在: {root}")
    except PermissionError:
        raise CommandError(f"没有权限访问目录: {root}")
    except OSError as exc:
        raise CommandError(f"无法读取目录: {exc}")
