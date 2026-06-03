#!/bin/bash
# ============================================================
# TollAuditExpress 部署脚本
# 用法: ./deploy.sh [code|full]
#   code  - 仅更新代码（默认，适合日常迭代）
#   full  - 重新构建 Docker 镜像并部署（适合首次部署或依赖变更）
#
# 前置条件:
#   1. 本地已安装 rsync, ssh, docker
#   2. 目标服务器已安装 docker, docker-compose
#   3. SSH 免密登录目标服务器
# ============================================================

set -e

# ---- 配置（按实际环境修改） ----
BUILD_SERVER="${BUILD_SERVER:-root@192.168.1.100}"      # 构建服务器（有 Docker）
TARGET_SERVER="${TARGET_SERVER:-root@10.0.0.10}"        # 目标服务器（运行服务）
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="/opt/toll-audit-build"
TARGET_DIR="/opt/toll-audit"
IMAGE_NAME="toll-audit-express:latest"
CONTAINER_NAME="toll-audit-express"
SERVICE_PORT="${SERVICE_PORT:-8000}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

UPDATE_TYPE="${1:-code}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TollAuditExpress 部署脚本${NC}"
echo -e "${GREEN}  模式: ${UPDATE_TYPE}${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# ---- 检查前端是否已构建 ----
check_frontend_build() {
    if [ ! -d "$LOCAL_DIR/apps/web/dist" ]; then
        echo -e "${YELLOW}前端未构建，正在构建...${NC}"
        cd "$LOCAL_DIR/apps/web"
        npm install --legacy-peer-deps 2>/dev/null || true
        npm run build
        cd "$LOCAL_DIR"
    fi
}

# ---- 模式1: 仅更新代码 ----
if [ "$UPDATE_TYPE" = "code" ]; then
    echo -e "${GREEN}[1/4] 构建前端（如未构建）...${NC}"
    check_frontend_build

    echo -e "${GREEN}[2/4] 同步代码到目标服务器...${NC}"
    rsync -avz --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='node_modules' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='apps/api/data/*.db' \
        --exclude='apps/api/data/*.db-journal' \
        --exclude='*.tar.gz' \
        --exclude='.claude' \
        "$LOCAL_DIR/" "$TARGET_SERVER:$TARGET_DIR/"

    echo -e "${GREEN}[3/4] 复制代码到容器...${NC}"
    ssh "$TARGET_SERVER" "docker cp $TARGET_DIR/apps/api/. $CONTAINER_NAME:/app/apps/api/ && \
                          docker cp $TARGET_DIR/apps/web/dist/. $CONTAINER_NAME:/app/apps/web/dist/ && \
                          docker cp $TARGET_DIR/packages/. $CONTAINER_NAME:/app/packages/"

    echo -e "${GREEN}[4/4] 重启容器...${NC}"
    ssh "$TARGET_SERVER" "docker restart $CONTAINER_NAME"

    sleep 5
    echo -e "${GREEN}检查服务状态...${NC}"
    HTTP_CODE=$(ssh "$TARGET_SERVER" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$SERVICE_PORT/health 2>/dev/null || echo 000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ 部署成功，服务正常运行${NC}"
    else
        echo -e "${RED}✗ 服务可能未正常启动 (HTTP $HTTP_CODE)，请检查: docker logs $CONTAINER_NAME${NC}"
    fi

# ---- 模式2: 完整重建 ----
elif [ "$UPDATE_TYPE" = "full" ]; then
    echo -e "${GREEN}[1/6] 构建前端...${NC}"
    check_frontend_build

    echo -e "${GREEN}[2/6] 清理构建服务器旧镜像...${NC}"
    ssh "$BUILD_SERVER" "docker rmi $IMAGE_NAME 2>/dev/null || true; docker builder prune -af"

    echo -e "${GREEN}[3/6] 同步代码到构建服务器...${NC}"
    rsync -avz --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='node_modules' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='apps/api/data' \
        --exclude='*.tar.gz' \
        --exclude='.claude' \
        "$LOCAL_DIR/" "$BUILD_SERVER:$BUILD_DIR/"

    echo -e "${GREEN}[4/6] 构建 Docker 镜像...${NC}"
    ssh "$BUILD_SERVER" "cd $BUILD_DIR && docker build -t $IMAGE_NAME . 2>&1 | tail -10"

    echo -e "${GREEN}[5/6] 导出并传输镜像...${NC}"
    ssh "$BUILD_SERVER" "docker save $IMAGE_NAME -o $BUILD_DIR/toll-audit-express.tar"
    rsync -avz -e "ssh" "$BUILD_SERVER:$BUILD_DIR/toll-audit-express.tar" /tmp/
    rsync -avz -e "ssh" /tmp/toll-audit-express.tar "$TARGET_SERVER:/tmp/"

    echo -e "${GREEN}[6/6] 在目标服务器上部署...${NC}"
    ssh "$TARGET_SERVER" "
        docker stop $CONTAINER_NAME 2>/dev/null || true
        docker rm $CONTAINER_NAME 2>/dev/null || true
        docker rmi $IMAGE_NAME 2>/dev/null || true
        docker load -i /tmp/toll-audit-express.tar
        mkdir -p $TARGET_DIR/apps/api/data
        mkdir -p $TARGET_DIR/logs
        docker run -d \
            --name $CONTAINER_NAME \
            -p $SERVICE_PORT:8000 \
            -v $TARGET_DIR/apps/api/data:/app/apps/api/data \
            -v $TARGET_DIR/.env:/app/.env:ro \
            -v $TARGET_DIR/logs:/app/logs \
            --restart unless-stopped \
            $IMAGE_NAME
    "

    sleep 5
    echo -e "${GREEN}检查服务状态...${NC}"
    ssh "$TARGET_SERVER" "docker ps --format '{{.Names}}: {{.Status}}' | grep $CONTAINER_NAME"
    HTTP_CODE=$(ssh "$TARGET_SERVER" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$SERVICE_PORT/health 2>/dev/null || echo 000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ 完整部署成功，服务正常运行${NC}"
    else
        echo -e "${RED}✗ 服务可能未正常启动 (HTTP $HTTP_CODE)，请检查: docker logs $CONTAINER_NAME${NC}"
    fi

else
    echo -e "${RED}未知模式: $UPDATE_TYPE${NC}"
    echo "用法: ./deploy.sh [code|full]"
    echo "  code  - 仅更新代码（默认）"
    echo "  full  - 重新构建 Docker 镜像"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成${NC}"
echo -e "${GREEN}========================================${NC}"
