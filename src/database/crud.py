"""! @file crud.py
 @brief 审计日志 CRUD 操作

 提供审计日志的创建与查询接口，封装对 @ref AuditLog 模型的数据库操作。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from sqlalchemy.orm import Session

from src.database.models import AuditLog


def create_audit_log(
    db: Session,
    *,
    action: str,
    params: str,
    command: str,
    return_code: int,
    stdout: str = "",
    stderr: str = "",
) -> AuditLog:
    """! 创建一条审计日志记录

    @param db SQLAlchemy Session 对象
    @param action 操作类型标识
    @param params 请求参数的 JSON 字符串
    @param command 执行的系统命令字符串
    @param return_code 命令返回码
    @param stdout 命令标准输出内容，默认为空
    @param stderr 命令标准错误内容，默认为空
    @return 创建并持久化后的 AuditLog 对象
    """
    log = AuditLog(
        action=action,
        params=params,
        command=command,
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_audit_logs(db: Session, limit: int = 100) -> list[AuditLog]:
    """! 查询最近的审计日志记录

    按主键倒序排列，即最新的记录排在最前面。

    @param db SQLAlchemy Session 对象
    @param limit 返回记录数量上限，默认 100
    @return AuditLog 对象列表
    """
    return db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
