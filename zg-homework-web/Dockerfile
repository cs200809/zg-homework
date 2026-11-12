# ===== zg-tsp-web 镜像 =====
# 构建：docker build -t zg-tsp-web:1.0.0 .
# 运行：docker run -d -p 8080:80 zg-tsp-web:1.0.0

# --- 构建阶段 ---
FROM node:20-alpine AS builder

WORKDIR /app

# 依赖单独一层，利用缓存
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# --- 运行阶段（Nginx 托管静态产物）---
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]