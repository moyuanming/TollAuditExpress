#!/bin/bash
# ============================================================
# TollAuditExpress 部署脚本
# 用法: ./deploy.sh [code|full]
#   code  - 仅更新代码（默认，适合日常迭代）
#   full  - 重新构建 Docker 镜像并部署（适合首次部署或依赖变更）
#
# 三机拓扑：
#   - 本地 macOS（当前机器）= 调度端，同时连得通下面两台
#   - 159.138.100.157 (BUILD_SERVER)  = 构建机，跑 docker build
#   - 10.11.1.40    (TARGET_SERVER)  = 运行机，承载最终容器
#   - 约束：构建机 <-> 运行机 网络不通，必须经本地 macOS 中转
#
# 配置通过 deploy.config.env 注入（已 gitignore）。
#
# 前置条件:
#   1. 本地已安装 rsync, ssh, docker
#   2. 目标服务器已安装 docker
#   3. SSH 免密登录到两台服务器
#   4. 本地 .env 文件存在（仅 full/code 模式需要推送时）
# ============================================================

set -euo pipefail

# ---- 加载本地配置（deploy.config.env，已 gitignore） ----
_SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$_SELF_DIR/deploy.config.env" ]; then
    # shellcheck disable=SC1090
    source "$_SELF_DIR/deploy.config.env"
fi
unset _SELF_DIR

# ---- 配置（deploy.config.env 中的值会覆盖下面的默认值） ----
BUILD_SERVER="${BUILD_SERVER:-root@192.168.1.100}"        # 构建服务器（有 Docker）
TARGET_SERVER="${TARGET_SERVER:-root@10.0.0.10}"          # 目标服务器（运行服务）
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${BUILD_DIR:-/opt/toll-audit-build}"
TARGET_DIR="${TARGET_DIR:-/opt/toll-audit}"
IMAGE_NAME="${IMAGE_NAME:-toll-audit-express:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-toll-audit-express}"
SERVICE_PORT="${SERVICE_PORT:-8000}"
SSH_OPTS="${SSH_OPTS:-}"                                  # 留空则用 ssh 默认参数

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

UPDATE_TYPE="${1:-code}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TollAuditExpress 部署脚本${NC}"
echo -e "${GREEN}  模式: ${UPDATE_TYPE}${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  构建服务器: ${BUILD_SERVER}${NC}"
echo -e "${GREEN}  目标服务器: ${TARGET_SERVER}${NC}"
echo ""

# ---- 通用函数 ----

# 检查前端是否已构建
check_frontend_build() {
    if [ ! -d "$LOCAL_DIR/apps/web/dist" ]; then
        echo -e "${YELLOW}前端未构建，正在构建...${NC}"
        cd "$LOCAL_DIR/apps/web"
        npm install --legacy-peer-deps 2>/dev/null || true
        npm run build
        cd "$LOCAL_DIR"
    fi
}

# 把本地 .env 推送到目标服务器，600 权限
push_env_to_target() {
    if [ ! -f "$LOCAL_DIR/.env" ]; then
        echo -e "${YELLOW}  本地 .env 不存在，跳过推送（首次部署请准备 .env 后重跑）${NC}"
        return 0
    fi
    echo -e "${GREEN}  推送 .env 到 $TARGET_SERVER:$TARGET_DIR/.env (chmod 600)${NC}"
    ssh $SSH_OPTS "$TARGET_SERVER" "install -d -m 700 '$TARGET_DIR'"
    # scp 到临时文件，sed 把本地 macOS 路径替换为容器内路径，再移到正式位置
    scp $SSH_OPTS "$LOCAL_DIR/.env" "$TARGET_SERVER:$TARGET_DIR/.env.tmp"
    ssh $SSH_OPTS "$TARGET_SERVER" "
        sed -i 's|^GETMOVEOBU_PATH=.*|GETMOVEOBU_PATH=/app/models|' '$TARGET_DIR/.env.tmp' && \
        sed -i 's|^MODEL_PATH=.*|MODEL_PATH=/app/models/best_model.pth|' '$TARGET_DIR/.env.tmp' && \
        sed -i 's|^MAAS_API_URL=.*|MAAS_API_URL=http://10.11.110.26:9910/hwmaas/v1|' '$TARGET_DIR/.env.tmp' && \
        sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=http://10.11.1.40:8080,http://localhost:3000|' '$TARGET_DIR/.env.tmp' && \
        sed -i 's|^AUTH_ENABLED=.*|AUTH_ENABLED=false|' '$TARGET_DIR/.env.tmp' && \
        mv '$TARGET_DIR/.env.tmp' '$TARGET_DIR/.env' && \
        chmod 600 '$TARGET_DIR/.env' && \
        chown 1000:1000 '$TARGET_DIR/.env'
    "
}

# 推送 ML 模型文件到目标服务器
LOCAL_MODEL_PATH="${LOCAL_MODEL_PATH:-/Users/moyuanming/getmoveobu/best_model.pth}"
LOCAL_RESNET50_PATH="${LOCAL_RESNET50_PATH:-$HOME/.cache/torch/hub/checkpoints/resnet50-0676ba61.pth}"
push_models_to_target() {
    local pushed=0
    if [ -f "$LOCAL_MODEL_PATH" ]; then
        echo -e "${GREEN}  推送 best_model.pth 到 $TARGET_SERVER:$TARGET_DIR/models/ ${NC}"
        ssh $SSH_OPTS "$TARGET_SERVER" "install -d -m 755 '$TARGET_DIR/models'"
        scp $SSH_OPTS "$LOCAL_MODEL_PATH" "$TARGET_SERVER:$TARGET_DIR/models/"
        pushed=1
    else
        echo -e "${YELLOW}  本地模型 $LOCAL_MODEL_PATH 不存在，跳过${NC}"
    fi
    if [ -f "$LOCAL_RESNET50_PATH" ]; then
        echo -e "${GREEN}  推送 resnet50 到 $TARGET_SERVER:$TARGET_DIR/models/torch_cache/hub/checkpoints/ ${NC}"
        ssh $SSH_OPTS "$TARGET_SERVER" "install -d -m 755 '$TARGET_DIR/models/torch_cache/hub/checkpoints'"
        scp $SSH_OPTS "$LOCAL_RESNET50_PATH" "$TARGET_SERVER:$TARGET_DIR/models/torch_cache/hub/checkpoints/"
        pushed=1
    fi
    if [ "$pushed" = "1" ]; then
        ssh $SSH_OPTS "$TARGET_SERVER" "chown -R 1000:1000 '$TARGET_DIR/models'"
    fi
}

# 清理目标机上 image 名含 toll-audit、但容器名不是 $CONTAINER_NAME 的孤儿容器
cleanup_orphan_containers() {
    echo -e "${YELLOW}  清理目标机上的 toll-audit 旧容器...${NC}"
    ssh $SSH_OPTS "$TARGET_SERVER" "
        docker ps -a --format '{{.Names}} {{.Image}}' | \
            awk '\$2 ~ /toll-audit/ && \$1 != \"$CONTAINER_NAME\" {print \$1}' | \
            xargs -r docker rm -f 2>/dev/null || true
    "
}

# 健康检查；失败时把容器日志拉回来给本地看
healthcheck_or_dump_logs() {
    local http_code
    http_code=$(ssh $SSH_OPTS "$TARGET_SERVER" "curl -s -o /dev/null -w '%{http_code}' http://localhost:$SERVICE_PORT/health 2>/dev/null || echo 000")
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}  ✓ 服务健康 (HTTP $http_code)${NC}"
        return 0
    fi
    echo -e "${RED}  ✗ 服务可能未正常启动 (HTTP $http_code)，拉取最近 200 行日志:${NC}"
    echo "------------------------------------------------------------"
    ssh $SSH_OPTS "$TARGET_SERVER" "docker logs --tail 200 $CONTAINER_NAME 2>&1" || true
    echo "------------------------------------------------------------"
    return 1
}

# ---- 模式1: 仅更新代码 ----
if [ "$UPDATE_TYPE" = "code" ]; then
    echo -e "${GREEN}[1/5] 构建前端（如未构建）...${NC}"
    check_frontend_build

    echo -e "${GREEN}[2/5] 推送 .env（chmod 600）...${NC}"
    push_env_to_target

    echo -e "${GREEN}[2.5/5] 推送 ML 模型文件...${NC}"
    push_models_to_target

    echo -e "${GREEN}[3/5] 同步代码到目标服务器（tar+scp，排除 .env）...${NC}"
    tar czf /tmp/toll-audit-code.tar.gz \
        --exclude='.git' \
        --exclude='.env' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='node_modules' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='apps/api/data/*.db' \
        --exclude='apps/api/data/*.db-journal' \
        --exclude='*.tar.gz' \
        --exclude='.claude' \
        --exclude='deploy.config.env' \
        -C "$LOCAL_DIR" .
    scp $SSH_OPTS /tmp/toll-audit-code.tar.gz "$TARGET_SERVER:$TARGET_DIR/"
    ssh $SSH_OPTS "$TARGET_SERVER" "cd $TARGET_DIR && tar xzf toll-audit-code.tar.gz && rm toll-audit-code.tar.gz"
    rm -f /tmp/toll-audit-code.tar.gz

    echo -e "${GREEN}[4/5] 复制代码到容器...${NC}"
    ssh $SSH_OPTS "$TARGET_SERVER" "
        docker cp $TARGET_DIR/apps/api/. $CONTAINER_NAME:/app/apps/api/ && \
        docker cp $TARGET_DIR/apps/web/dist/. $CONTAINER_NAME:/app/apps/web/dist/ && \
        docker cp $TARGET_DIR/packages/. $CONTAINER_NAME:/app/packages/
    "

    echo -e "${GREEN}[5/5] 重启容器 + 健康检查...${NC}"
    ssh $SSH_OPTS "$TARGET_SERVER" "docker restart $CONTAINER_NAME"
    sleep 5
    healthcheck_or_dump_logs

# ---- 模式2: 完整重建 ----
elif [ "$UPDATE_TYPE" = "full" ]; then
    echo -e "${GREEN}[1/7] 构建前端...${NC}"
    check_frontend_build

    echo -e "${GREEN}[2/7] 清理构建服务器旧镜像...${NC}"
    ssh $SSH_OPTS "$BUILD_SERVER" "docker rmi $IMAGE_NAME 2>/dev/null || true; docker builder prune -af >/dev/null 2>&1 || true"

    echo -e "${GREEN}[3/7] 同步代码到构建服务器（排除 .env）...${NC}"
    rsync -avz --delete \
        -e "ssh $SSH_OPTS" \
        --exclude='.git' \
        --exclude='.env' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='node_modules' \
        --exclude='.pytest_cache' \
        --exclude='.ruff_cache' \
        --exclude='apps/api/data' \
        --exclude='*.tar.gz' \
        --exclude='.claude' \
        --exclude='deploy.config.env' \
        "$LOCAL_DIR/" "$BUILD_SERVER:$BUILD_DIR/"

    echo -e "${GREEN}[4/7] 在构建服务器上 docker build...${NC}"
    ssh $SSH_OPTS "$BUILD_SERVER" "cd $BUILD_DIR && docker build -t $IMAGE_NAME . 2>&1 | tail -15"

    echo -e "${GREEN}[5/7] 导出镜像 → 拉回本地 → 推到目标机（构建机↔目标机不通，本地中转）...${NC}"
    ssh $SSH_OPTS "$BUILD_SERVER" "docker save $IMAGE_NAME -o $BUILD_DIR/toll-audit-express.tar"
    rsync -avz -e "ssh $SSH_OPTS" "$BUILD_SERVER:$BUILD_DIR/toll-audit-express.tar" /tmp/
    # 用 scp 推到目标机（CentOS 7 默认没 rsync，scp 更可靠）
    ssh $SSH_OPTS "$TARGET_SERVER" "rm -f /tmp/toll-audit-express.tar" 2>/dev/null || true
    scp $SSH_OPTS /tmp/toll-audit-express.tar "$TARGET_SERVER:/tmp/"

    echo -e "${GREEN}[6/7] 在目标服务器上加载并启动新容器 + 推 .env + 推模型 + 清孤儿容器...${NC}"
    push_env_to_target
    push_models_to_target
    ssh $SSH_OPTS "$TARGET_SERVER" "
        set -e
        docker stop $CONTAINER_NAME 2>/dev/null || true
        docker rm $CONTAINER_NAME 2>/dev/null || true
        docker rmi $IMAGE_NAME 2>/dev/null || true
        docker load -i /tmp/toll-audit-express.tar
        install -d -m 755 $TARGET_DIR/apps/api/data
        install -d -m 755 $TARGET_DIR/logs
        chown -R 1000:1000 $TARGET_DIR/apps/api/data $TARGET_DIR/logs
        docker run -d \
            --name $CONTAINER_NAME \
            -p $SERVICE_PORT:8000 \
            -v $TARGET_DIR/apps/api/data:/app/apps/api/data \
            -v $TARGET_DIR/.env:/app/.env:ro \
            -v $TARGET_DIR/models:/app/models:ro \
            -v $TARGET_DIR/models/torch_cache:/home/appuser/.cache/torch \
            -v $TARGET_DIR/logs:/app/logs \
            --restart unless-stopped \
            $IMAGE_NAME
    "
    cleanup_orphan_containers

    echo -e "${GREEN}[7/7] 健康检查...${NC}"
    sleep 5
    ssh $SSH_OPTS "$TARGET_SERVER" "docker ps --format '{{.Names}}: {{.Status}}' | grep $CONTAINER_NAME" || true
    healthcheck_or_dump_logs

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
