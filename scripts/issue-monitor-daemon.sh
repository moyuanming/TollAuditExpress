#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Monitor Daemon
# 
# 自恢复常驻进程，每5分钟轮询 GitHub Issues。
# 检测到待处理 issue 时输出通知（被 Hermes 后台进程捕获）。
# 无 issue 时静默。
#
# 启动: bash scripts/issue-monitor-daemon.sh
# ============================================================================

set -uo pipefail

INTERVAL=300  # 5 minutes
REPO_DIR="$HOME/TollAuditExpress"
LOG="/tmp/issue-monitor-daemon.log"

echo "[$(date)] Daemon started, interval=${INTERVAL}s" >> "$LOG"

while true; do
    cd "$REPO_DIR" || { echo "[$(date)] ERROR: cannot cd to $REPO_DIR" >> "$LOG"; sleep "$INTERVAL"; continue; }

    # --- Phase 1: 恢复卡住的 issue ---
    RECOVERED=0
    while IFS= read -r NUM; do
        [ -z "$NUM" ] && continue
        gh issue edit "$NUM" --remove-label "ai-processing" --add-label "ai-failed" 2>/dev/null || true
        gh issue comment "$NUM" --body "⚠️ 处理超时，已重置为待处理。" 2>/dev/null || true
        RECOVERED=$((RECOVERED + 1))
        echo "[$(date)] Recovered stuck issue #$NUM" >> "$LOG"
    done < <(gh issue list --state open --label "ai-processing" \
        --json number,updatedAt --limit 20 \
        --jq '.[] | select(
            ((now - (.updatedAt | sub("\\+[0-9:]+"; "Z") | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime)) / 60) > 10
        ) | .number' 2>/dev/null)

    # --- Phase 2: 检测待处理 issue ---
    ISSUES=""
    ISSUES=$(python3 -c "
import subprocess, json
try:
    out = subprocess.check_output(['gh','issue','list','--state','open','--json','number,title,body,labels','--limit','20'], stderr=subprocess.DEVNULL, text=True)
    issues = json.loads(out) if out.strip() else []
except: issues = []
for i in issues:
    labels = [l['name'] for l in i.get('labels',[])]
    ai = [l for l in labels if l.startswith('ai-')]
    if not ai or 'ai-failed' in labels:
        body = i.get('body','').replace('\n',' ')[:200]
        print(f\"{i['number']}|{i.get('title','')}|{body}\")
" 2>/dev/null)

    # --- 输出通知 ---
    if [ $RECOVERED -gt 0 ] || [ -n "$ISSUES" ]; then
        echo "📋 [Issue Monitor] 检测结果:"
        [ $RECOVERED -gt 0 ] && echo "  🔄 恢复了 $RECOVERED 个卡住的 issue"
        COUNT=$(echo "$ISSUES" | grep -c . 2>/dev/null || echo 0)
        [ "$COUNT" -gt 0 ] && echo "  📌 待处理 issue: $COUNT 个"
        echo "$ISSUES" | while IFS='|' read -r NUM TITLE BODY; do
            [ -z "$NUM" ] && continue
            echo "  - #$NUM: $TITLE"
        done
        echo ""
        echo "请处理以上 issue。对每个 issue 执行:"
        echo "  1. bash scripts/issue-processor.sh mark_processing NUMBER"
        echo "  2. delegate_task 修复代码"
        echo "  3. bash scripts/issue-processor.sh run_tests"
        echo "  4. bash scripts/issue-processor.sh commit_changes NUMBER TITLE"
        echo "  5. bash scripts/issue-processor.sh finish_success/finish_testfail/finish_failed"
        echo "[$(date)] Found $COUNT issue(s), $RECOVERED recovered" >> "$LOG"
    else
        echo "[$(date)] No issues to process" >> "$LOG"
    fi

    sleep "$INTERVAL"
done
