"""! @file core.py
 @brief SQLAlchemy 数据库核心配置

 初始化 SQLite 数据库引擎、会话工厂和声明式基类，确保数据目录存在。

 @author 李泽源、谢子墨
 @date 2026
 @copyright MIT License
 @note 武汉大学开源软件与技术课程 2026
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


## 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

## 数据目录，用于存放 SQLite 数据库文件
DATA_DIR = BASE_DIR / "data"

## SQLite 数据库文件路径
DB_PATH = DATA_DIR / "storage_manager.sqlite3"

## 自动创建数据目录
DATA_DIR.mkdir(parents=True, exist_ok=True)

## SQLAlchemy 数据库连接 URL
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

## 数据库引擎实例
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

## 会话工厂，用于创建数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

## 声明式基类，所有 ORM 模型均继承自此基类
Base = declarative_base()
