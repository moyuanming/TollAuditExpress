# TollAuditExpress — 高速公路收费稽核系统
# 多阶段构建：Node.js 构建前端 + Python 运行后端

# ============================================================
# Stage 1: 构建前端 (Node.js)
# ============================================================
FROM docker.1ms.run/library/node:18-slim AS builder-node

WORKDIR /build

# 安装依赖（利用 Docker 层缓存）
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install 2>/dev/null || npm install --legacy-peer-deps

# 复制前端源码并构建
COPY apps/web/ ./
RUN npm run build

# ============================================================
# Stage 2: 安装 Python 依赖
# ============================================================
FROM docker.1ms.run/library/python:3.10-slim AS builder-python

# 使用国内镜像源
RUN pip config set global.index-url https://docker.1ms.run/pypi/simple/ && \
    pip config set global.extra-index-url https://pypi.org/simple/ && \
    pip config set global.trusted-host "docker.1ms.run pypi.org"

# PyTorch CPU 版本（减小镜像体积 ~200MB vs CUDA ~800MB）
RUN pip install --no-cache-dir --user torch==2.3.1+cpu torchvision==0.18.1+cpu \
    -f https://download.pytorch.org/whl/cpu/torch_stable.html || \
    pip install --no-cache-dir --user torch==2.3.1 torchvision==0.18.1

# 编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（跳过 torch）
COPY apps/api/requirements.txt /tmp/
RUN grep -v '^torch' /tmp/requirements.txt | grep -v '^torchvision' > /tmp/requirements_filtered.txt && \
    pip install --no-cache-dir --user -r /tmp/requirements_filtered.txt

# ============================================================
# Stage 3: 生产镜像
# ============================================================
FROM docker.1ms.run/library/python:3.10-slim

# 运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN useradd -m -u 1000 appuser

WORKDIR /app

# 从构建阶段复制依赖
COPY --from=builder-python /root/.local /home/appuser/.local

# 复制后端代码
COPY --chown=appuser:appuser apps/api/ ./apps/api/
COPY --chown=appuser:appuser packages/ ./packages/

# 复制前端构建产物
COPY --from=builder-node --chown=appuser:appuser /build/dist ./apps/web/dist/

# 复制模型文件（如存在）
COPY --chown=appuser:appuser yolov8n.pt* ./

# 创建数据目录
RUN mkdir -p /app/apps/api/data && chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 环境变量
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FRONTEND_DIR=/app/apps/web/dist \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python3", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
