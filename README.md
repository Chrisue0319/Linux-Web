# Linux 存储管理 Web 面板

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009485.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

基于 Python、FastAPI、SQLAlchemy 和 SQLite 的轻量级 Linux 存储管理 Web 界面，提供块设备查看、挂载/卸载、文件系统格式化与扩容、目录管理、权限调整以及操作审计日志等功能。

> **作者**：李泽源、谢子墨  
> **课程**：武汉大学开源软件与技术课程 2026

---

## 功能特性

- **概览**：查看块设备、挂载点和磁盘空间使用情况
- **挂载管理**：挂载、卸载存储设备，支持强制卸载
- **文件系统**：创建文件系统（ext2/3/4、xfs、btrfs），支持卷标设置
- **空间扩容**：扩展 ext、xfs、btrfs 文件系统
- **目录管理**：浏览、创建、删除目录，支持递归删除
- **权限设置**：调整目录/文件权限和属主/属组
- **审计日志**：自动记录所有管理操作，便于回溯与安全审计

---

## 系统架构

```
用户浏览器
    ↓
Nginx (HTTPS, 可选)
    ↓
uvicorn / FastAPI (app.main:app)
    ↓
┌─────────────┴─────────────┐
│                           │
app/storage.py         src/database/*
业务逻辑层              SQLAlchemy ORM
│                           │
subprocess/lsblk/           SQLite
mount/umount/mkfs           (审计日志)
```

分层说明：

| 文件/目录 | 职责 |
|-----------|------|
| `app/main.py` | FastAPI 路由层：认证、请求处理、审计日志记录、异常处理 |
| `app/storage.py` | 业务逻辑层：系统命令封装、路径安全校验 |
| `src/schemas.py` | Pydantic 数据模型层：请求校验与中文错误消息 |
| `src/database/core.py` | SQLAlchemy 引擎、会话、声明式基类 |
| `src/database/models.py` | ORM 数据模型：审计日志表 |
| `src/database/crud.py` | 数据库 CRUD 操作 |
| `app/static/` | 前端静态资源（HTML/CSS/JS） |
| `tests/` | 测试套件 |
| `deploy/` | systemd 服务模板与部署脚本 |

---

## 快速开始

### 环境要求

- Python 3.12+
- Linux 操作系统（挂载/格式化等操作依赖 Linux 系统命令）
- root 权限（用于执行 mount/umount/mkfs 等管理操作）

### 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 运行

```bash
STORAGE_MANAGER_PASSWORD=change-me uvicorn app.main:app --host 0.0.0.0 --port 8010
```

默认用户名：`admin`，密码由环境变量 `STORAGE_MANAGER_PASSWORD` 设置。

---

## 测试

```bash
pip install pytest
pytest
```

> 注：写操作测试需要 root 权限，当前测试套件主要覆盖参数校验、认证和只读接口。

---

## Docker 运行

```bash
docker build -t storage-manager .
docker run -p 8010:8010 -e STORAGE_MANAGER_PASSWORD=change-me storage-manager
```

---

## 部署

仓库包含 `deploy/storage-manager.service` systemd 服务模板和 `deploy/deploy.sh` 部署脚本。

```bash
cd /opt/storage-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp deploy/storage-manager.service /etc/systemd/system/storage-manager.service
systemctl daemon-reload
systemctl enable --now storage-manager
```

生产环境建议通过 Nginx 等反向代理提供 HTTPS，并不要将后端端口直接暴露到公网。

---

## 安全说明

- 所有写操作接口均通过 HTTP Basic Auth 保护
- 使用 `secrets.compare_digest` 防止时序攻击
- 关键系统目录（如 `/`、`/bin`、`/etc`、`/usr`、`/var` 等）禁止创建/删除/权限修改
- 输入参数经过 Pydantic 校验，422 错误已翻译为中文提示

---

## 文档

- [`README.md`](README.md)：项目简介与快速开始
- [`用户手册.md`](用户手册.md)：详细功能使用说明
- [`CHANGELOG.md`](CHANGELOG.md)：版本更新记录
- [`LICENSE`](LICENSE)：MIT 许可证
- [`deploy/storage-manager.service`](deploy/storage-manager.service)：systemd 服务模板
- 代码注释采用 Doxygen 风格，可生成 API 文档

---

## 许可证

本项目采用 [MIT 许可证](LICENSE) 开源。

---

## 致谢

项目架构参考 [easy-store](https://github.com/KingAkeem/easy-store) 设计。
