#!/bin/bash
# ============================================================
# 联通性自检：SSH 到构建机 & 目标机，验证 docker 可用
# 用法: ./scripts/check-conn.sh
# 退出码: 0=全部 OK，非 0=任一失败
# ============================================================

set -euo pipefail

_SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$_SELF_DIR/.." && pwd)"
unset _SELF_DIR

if [ -f "$ROOT_DIR/deploy.config.env" ]; then
    # shellcheck disable=SC1090
    source "$ROOT_DIR/deploy.config.env"
fi

BUILD_SERVER="${BUILD_SERVER:-root@192.168.1.100}"
TARGET_SERVER="${TARGET_SERVER:-root@10.0.0.10}"
SSH_OPTS="${SSH_OPTS:-}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

FAIL=0

probe() {
    local label="$1"
    local target="$2"
    echo ""
    echo -e "${YELLOW}--- $label ($target) ---${NC}"
    if ! ssh $SSH_OPTS -o ConnectTimeout=8 "$target" "echo CONNECTED_OK && uname -n && which docker >/dev/null 2>&1 && docker --version || echo 'docker missing'"; then
        echo -e "${RED}✗ $label 不可达${NC}"
        FAIL=1
        return
    fi
    echo -e "${GREEN}✓ $label OK${NC}"
}

probe_target_containers() {
    local target="$1"
    echo ""
    echo -e "${YELLOW}--- 目标机已有容器（前 5 条） ---${NC}"
    ssh $SSH_OPTS -o ConnectTimeout=8 "$target" "docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null | head -5" || true
}

echo "=========================================="
echo "  TollAuditExpress 联通性自检"
echo "  构建机: $BUILD_SERVER"
echo "  目标机: $TARGET_SERVER"
echo "=========================================="

probe "构建服务器" "$BUILD_SERVER"
probe "目标服务器" "$TARGET_SERVER"
probe_target_containers "$TARGET_SERVER"

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✓ 全部联通性检查通过${NC}"
    exit 0
else
    echo -e "${RED}✗ 联通性检查失败${NC}"
    exit 1
fi
