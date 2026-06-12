# Linux Storage Manager - Docker 镜像构建文件
#
# 作者：李泽源、谢子墨
# 课程：武汉大学开源软件与技术课程 2026
# 许可证：MIT
#
# 构建：docker build -t storage-manager .
# 运行：docker run -p 8010:8010 -e STORAGE_MANAGER_PASSWORD=change-me storage-manager

FROM python:3.12

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8010

CMD [ "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010" ]
