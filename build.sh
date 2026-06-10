#!/bin/bash
# ============================================================
# TollAuditExpress 构建脚本
# 编译前端 → 打包发布文件 → 生成 tar.gz 发布包
# ============================================================

set -e

# ---- 加载本地部署配置（deploy.config.env，已 gitignore），仅用于打印目标信息 ----
_SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$_SELF_DIR/deploy.config.env" ]; then
    # shellcheck disable=SC1090
    source "$_SELF_DIR/deploy.config.env"
fi
unset _SELF_DIR

BUILD_SERVER="${BUILD_SERVER:-<未配置>}"
TARGET_SERVER="${TARGET_SERVER:-<未配置>}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_NAME="toll-audit-express-$(date +%Y%m%d-%H%M%S)"
BUILD_DIR="$PROJECT_DIR/build_temp"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TollAuditExpress 发布构建${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# ---- 1. 构建前端 ----
echo -e "${GREEN}[1/5] 构建前端...${NC}"

if [ ! -f "$PROJECT_DIR/apps/web/package.json" ]; then
    echo -e "${RED}错误: 找不到 apps/web/package.json${NC}"
    exit 1
fi

cd "$PROJECT_DIR/apps/web"

# 安装依赖（如果 node_modules 不存在）
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}  安装前端依赖...${NC}"
    npm install --legacy-peer-deps
fi

# 构建
echo "  npm run build..."
npm run build

if [ ! -d "dist" ]; then
    echo -e "${RED}错误: 前端构建失败，未生成 dist 目录${NC}"
    exit 1
fi

echo -e "${GREEN}  前端构建完成${NC}"

# ---- 2. 检查必要文件 ----
echo -e "${GREEN}[2/5] 检查必要文件...${NC}"

cd "$PROJECT_DIR"

required_files=(
    "apps/api/main.py"
    "apps/api/requirements.txt"
    "apps/web/dist/index.html"
    "packages/contracts/types/schemas.py"
)

for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}错误: 缺少必要文件 $file${NC}"
        exit 1
    fi
done

echo -e "${GREEN}  所有必要文件检查通过${NC}"

# ---- 3. 创建发布目录 ----
echo -e "${GREEN}[3/5] 准备发布文件...${NC}"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$RELEASE_NAME"

# 复制后端代码（排除不需要的文件）
rsync -a \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    --exclude='data/*.db' \
    --exclude='data/*.db-journal' \
    "$PROJECT_DIR/apps/api/" "$BUILD_DIR/$RELEASE_NAME/apps/api/"

# 复制前端构建产物
mkdir -p "$BUILD_DIR/$RELEASE_NAME/apps/web/dist"
rsync -a "$PROJECT_DIR/apps/web/dist/" "$BUILD_DIR/$RELEASE_NAME/apps/web/dist/"

# 复制共享包
rsync -a \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    "$PROJECT_DIR/packages/" "$BUILD_DIR/$RELEASE_NAME/packages/"

# 复制部署文件
cp "$PROJECT_DIR/Dockerfile" "$BUILD_DIR/$RELEASE_NAME/"
cp "$PROJECT_DIR/docker-compose.yml" "$BUILD_DIR/$RELEASE_NAME/"
cp "$PROJECT_DIR/.env.example" "$BUILD_DIR/$RELEASE_NAME/.env.example"

# 复制模型文件（如存在）
if [ -f "$PROJECT_DIR/yolov8n.pt" ]; then
    echo -e "${YELLOW}  注意: yolov8n.pt (~6.5MB) 将包含在发布包中${NC}"
    cp "$PROJECT_DIR/yolov8n.pt" "$BUILD_DIR/$RELEASE_NAME/"
fi

# 创建 .env 模板
cp "$PROJECT_DIR/.env.example" "$BUILD_DIR/$RELEASE_NAME/.env"

# 复制 deploy.sh（从源目录复制，如果存在）
if [ -f "$PROJECT_DIR/deploy.sh" ]; then
    cp "$PROJECT_DIR/deploy.sh" "$BUILD_DIR/$RELEASE_NAME/"
    chmod +x "$BUILD_DIR/$RELEASE_NAME/deploy.sh"
fi

echo -e "${GREEN}  发布文件准备完成${NC}"

# ---- 4. 打包 ----
echo -e "${GREEN}[4/5] 打包发布包...${NC}"

cd "$BUILD_DIR"
tar -czf "$PROJECT_DIR/$RELEASE_NAME.tar.gz" "$RELEASE_NAME"

if [ ! -f "$PROJECT_DIR/$RELEASE_NAME.tar.gz" ]; then
    echo -e "${RED}错误: 打包失败${NC}"
    rm -rf "$BUILD_DIR"
    exit 1
fi

# 检查包大小
SIZE=$(stat -f%z "$PROJECT_DIR/$RELEASE_NAME.tar.gz" 2>/dev/null || stat -c%s "$PROJECT_DIR/$RELEASE_NAME.tar.gz" 2>/dev/null)
SIZE_MB=$((SIZE / 1024 / 1024))
echo -e "${GREEN}  发布包大小: ${SIZE_MB}MB${NC}"

# ---- 5. 清理 ----
echo -e "${GREEN}[5/5] 清理临时文件...${NC}"
rm -rf "$BUILD_DIR"

# ---- 完成 ----
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  构建完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "发布包: ${GREEN}$PROJECT_DIR/$RELEASE_NAME.tar.gz${NC}"
echo ""
echo -e "${YELLOW}部署步骤:${NC}"
echo -e "  1. 将发布包传输到目标服务器"
echo -e "     scp $RELEASE_NAME.tar.gz user@server:/opt/"
echo ""
echo -e "  2. 在目标服务器上解压"
echo -e "     tar -xzf $RELEASE_NAME.tar.gz"
echo -e "     cd $RELEASE_NAME"
echo ""
echo -e "  3. 配置环境变量"
echo -e "     cp .env.example .env"
echo -e "     vim .env   # 填写 DB_HOST, DB_USER, DB_PASSWORD 等"
echo ""
echo -e "  4. 构建并启动"
echo -e "     docker-compose up -d --build"
echo ""
echo -e "  5. 检查服务状态"
echo -e "     docker-compose ps"
echo -e "     curl http://localhost:8000/health"
echo ""
