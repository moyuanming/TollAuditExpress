#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Poller
# 
# 被 Hermes Cron Job 调用，检测新的 GitHub Issue 并输出 JSON 列表。
# 实际的修复工作由 Hermes agent 通过 delegate_task 完成。
# ============================================================================

set -euo pipefail

REPO_DIR="$HOME/TollAuditExpress"
cd "$REPO_DIR"

# Find open issues without ai-processing or ai-fixed labels
ISSUES_JSON=$(gh issue list \
    --state open \
    --json number,title,labels,body \
    --limit 20 \
    --jq '[.[] | select(
        (.labels | map(.name) | index("ai-processing") | not) and
        (.labels | map(.name) | index("ai-fixed") | not)
    )] | map({number, title, body})' 2>/dev/null || echo '[]')

# Output the JSON for the agent to process
echo "$ISSUES_JSON"
