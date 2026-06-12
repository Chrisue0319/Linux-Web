"""! @file models.py
 @brief SQLAlchemy ORM 数据模型

 定义审计日志表 @c audit_logs 的结构，用于持久化记录所有管理操作。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from sqlalchemy import Column, DateTime, Integer, String, func

from src.database.core import Base


class AuditLog(Base):
    """! 审计日志 ORM 模型

    记录每一次管理操作的类型、参数、执行命令、返回码及输出信息。

    @extends Base SQLAlchemy 声明式基类
    """

    ## 数据库表名
    __tablename__ = "audit_logs"

    ## 自增主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    ## 操作类型，如 mount、unmount、make_filesystem 等
    action = Column(String, nullable=False)

    ## 请求参数的 JSON 字符串
    params = Column(String, nullable=False)

    ## 实际执行的系统命令字符串
    command = Column(String, nullable=False)

    ## 命令返回码，0 表示成功
    return_code = Column(Integer, nullable=False)

    ## 命令标准输出内容
    stdout = Column(String, default="")

    ## 命令标准错误内容
    stderr = Column(String, default="")

    ## 记录创建时间，默认使用数据库当前时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
