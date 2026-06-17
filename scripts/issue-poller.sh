#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Monitor — launchd 调用入口
# 
# 被 macOS launchd 每5分钟调用一次。
# 检测到待处理 issue 时写通知文件，主 agent 通过 cron 读取处理。
# 无 issue 时静默。
# ============================================================================

set -uo pipefail
cd "$HOME/TollAuditExpress" || exit 1

NOTICE_FILE="/tmp/toll-audit-issue-notice.txt"
RECOVERED=0
ISSUES=()

# --- Phase 1: 恢复卡住的 issue ---
while IFS= read -r NUM; do
    [ -z "$NUM" ] && continue
    gh issue edit "$NUM" --remove-label "ai-processing" --add-label "ai-failed" 2>/dev/null || true
    gh issue comment "$NUM" --body "⚠️ 处理超时，已重置为待处理。" 2>/dev/null || true
    RECOVERED=$((RECOVERED + 1))
done < <(gh issue list --state open --label "ai-processing" \
    --json number,updatedAt --limit 20 \
    --jq '.[] | select(
        ((now - (.updatedAt | sub("\\+[0-9:]+"; "Z") | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime)) / 60) > 10
    ) | .number' 2>/dev/null)

# --- Phase 2: 检测待处理 issue ---
while IFS='|' read -r NUM TITLE BODY; do
    [ -z "$NUM" ] && continue
    ISSUES+=("$NUM|$TITLE|$BODY")
done < <(python3 -c "
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

# --- 写通知文件 ---
if [ $RECOVERED -gt 0 ] || [ ${#ISSUES[@]} -gt 0 ]; then
    {
        echo "[$(date '+%Y-%m-%d %H:%M')] 检测结果:"
        [ $RECOVERED -gt 0 ] && echo "  恢复了 $RECOVERED 个卡住的 issue"
        [ ${#ISSUES[@]} -gt 0 ] && echo "  待处理 issue: ${#ISSUES[@]} 个"
        for issue in "${ISSUES[@]}"; do
            IFS='|' read -r NUM TITLE BODY <<< "$issue"
            echo "  #$NUM|$TITLE"
        done
    } > "$NOTICE_FILE"
else
    # 无待处理 issue，清空通知
    rm -f "$NOTICE_FILE" 2>/dev/null
fi
