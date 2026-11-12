# ===== zg-homework-server 镜像 =====
# 构建：docker build -t zg-homework-server:1.0.0 .
# 运行及持久化挂卷说明见 README.md。

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖单独一层，利用缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 源码
COPY . .

# 数据与上传目录（生产建议挂卷）
RUN mkdir -p /app/app/data /app/app/uploads

EXPOSE 8000

# 健康检查为 POST-only，必须显式指定 method。
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/homework_api/health', method='POST'))" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]