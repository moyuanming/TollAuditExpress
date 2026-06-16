#!/usr/bin/env bash
# ============================================================================
# Cron Job Watchdog — 纯脚本版，不依赖 LLM
#
# 监控 toll-audit-issue-monitor 的运行状态，自动修复异常。
# 设计为 no_agent=True 的 cron job，避免 LLM 限流导致看门狗本身失效。
#
# 修复策略:
#   - 暂停 → 自动 resume
#   - 已完成但无下次调度 → 自动 resume
#   - 上次运行错误 → 仅报告（可能是临时限流，等自动重试）
#   - 一切正常 → 静默（stdout 为空，cron 不发送消息）
# ============================================================================

set -uo pipefail

TARGET_NAME="toll-audit-issue-monitor"
HERMES_CRON_OUTPUT=$(hermes cron list --all 2>&1)

# --- 解析目标 job 信息 ---
JOB_ID=$(echo "$HERMES_CRON_OUTPUT" | grep -B1 "$TARGET_NAME" | head -1 | awk '{print $1}')
if [ -z "$JOB_ID" ]; then
    echo "❌ [CRITICAL] 目标 job '$TARGET_NAME' 不存在！可能被删除了。"
    exit 0
fi

# 提取方括号状态
BRACKET_STATE=$(echo "$HERMES_CRON_OUTPUT" | grep "$JOB_ID" | grep -o '\[.*\]' | tr -d '[]')

# 提取 Next run
NEXT_RUN=$(echo "$HERMES_CRON_OUTPUT" | grep -A10 "$TARGET_NAME" | grep "Next run:" | sed 's/.*Next run:\s*//' | awk '{print $1}')

# 提取 Last run 及错误
LAST_RUN_LINE=$(echo "$HERMES_CRON_OUTPUT" | grep -A10 "$TARGET_NAME" | grep "Last run:")
LAST_STATUS="unknown"
ERROR_DETAIL=""
if echo "$LAST_RUN_LINE" | grep -q "error:"; then
    LAST_STATUS="error"
    ERROR_DETAIL=$(echo "$LAST_RUN_LINE" | sed 's/.*error: //' | head -c 200)
elif [ -n "$LAST_RUN_LINE" ]; then
    LAST_STATUS="success"
fi

# --- 修复逻辑 ---
FIXED=0
MESSAGES=()

# 情况1: job 被 paused
if [ "$BRACKET_STATE" = "paused" ]; then
    RESUME_OUT=$(hermes cron resume "$JOB_ID" 2>&1)
    if echo "$RESUME_OUT" | grep -qi "resumed\|success"; then
        MESSAGES+=("🔧 已自动 resume 暂停的 job $JOB_ID")
        FIXED=1
    else
        MESSAGES+=("❌ resume 失败: $RESUME_OUT")
    fi
fi

# 情况2: job 已完成但没有下次调度 (stopped after error)
if [ "$BRACKET_STATE" = "completed" ] && [ "$NEXT_RUN" = "None" ]; then
    RESUME_OUT=$(hermes cron resume "$JOB_ID" 2>&1)
    if echo "$RESUME_OUT" | grep -qi "resumed\|success"; then
        MESSAGES+=("🔧 已自动恢复停止调度的 job $JOB_ID (completed + no next_run)")
        FIXED=1
    else
        MESSAGES+=("❌ 恢复失败: $RESUME_OUT")
    fi
fi

# 情况3: job 状态异常 (不是 active/paused/completed)
if [ "$BRACKET_STATE" != "active" ] && [ "$BRACKET_STATE" != "paused" ] && [ "$BRACKET_STATE" != "completed" ]; then
    MESSAGES+=("⚠️ 未知状态: [$BRACKET_STATE]，尝试 resume")
    RESUME_OUT=$(hermes cron resume "$JOB_ID" 2>&1)
    if echo "$RESUME_OUT" | grep -qi "resumed\|success"; then
        MESSAGES+=("🔧 已 resume")
        FIXED=1
    else
        MESSAGES+=("❌ resume 失败: $RESUME_OUT")
    fi
fi

# --- 输出 ---
# 静默规则: 一切正常时不输出 (cron no_agent=True 不发送消息)
# 只在有问题时输出

if [ ${#MESSAGES[@]} -gt 0 ]; then
    echo "🐕 [Watchdog] toll-audit-issue-monitor 状态检查:"
    for msg in "${MESSAGES[@]}"; do
        echo "  $msg"
    done
fi

# 如果上次运行有错误，也报告 (但不自动修复，等自然重试)
if [ "$LAST_STATUS" = "error" ] && [ ${#MESSAGES[@]} -eq 0 ]; then
    echo "⚠️ [Watchdog] 上次运行出错 (等待自动重试): $ERROR_DETAIL"
fi
