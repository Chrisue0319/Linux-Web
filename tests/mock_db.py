"""! @file mock_db.py
 @brief 测试用内存数据库

 为测试提供基于 SQLite 内存数据库的 SQLAlchemy 引擎和会话工厂，
 并自动创建所有表结构。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.core import Base


## 内存 SQLite 连接 URL
SQLALCHEMY_DATABASE_URL = "sqlite://"

## 测试用数据库引擎，使用 StaticPool 保证同一线程内会话共享
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

## 测试用会话工厂
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

## 创建所有表
Base.metadata.create_all(bind=engine)
