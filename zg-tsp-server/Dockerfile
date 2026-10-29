# ===== zg-tsp-server 镜像 =====
# 构建：docker build -t zg-tsp-server:1.0.0 .
# 运行：docker run -d -p 8000:8000 --env-file .env zg-tsp-server:1.0.0

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

# /health 是 POST-only（全站 POST-only 设计，见 app/main.py），必须显式指定 method，
# 否则默认 GET 会拿到 405，容器被永远判定为不健康。
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/health', method='POST'))" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]