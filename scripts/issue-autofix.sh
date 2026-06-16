#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Auto-Fix (一体化闭环版)
# 
# 完整闭环：检测 → 修复 → 测试 → 提交 → 关闭
# 被 Cron Job 直接调用，无需 agent 编排。
# 
# AI 修复方式: Hermes delegate_task (通过 hermes CLI)
# ============================================================================

set -uo pipefail
REPO_DIR="$HOME/TollAuditExpress"
STUCK_MINUTES="${1:-10}"
MAX_ISSUES="${2:-3}"
cd "$REPO_DIR"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# ── Phase 1: Recover stuck issues ────────────────────────────────────────────
gh issue list --state open --label "ai-processing" \
    --json number,updatedAt --limit 20 \
    --jq ".[] | select(
        ((now - (.updatedAt | sub(\"\\+[0-9:]+\"; \"Z\") | strptime(\"%Y-%m-%dT%H:%M:%SZ\") | mktime)) / 60) > $STUCK_MINUTES
    ) | .number" 2>/dev/null | while read NUM; do
    log "[RECOVER] #$NUM stuck, resetting"
    gh issue edit "$NUM" --remove-label "ai-processing" --add-label "ai-failed" 2>/dev/null || true
    gh issue comment "$NUM" --body "⚠️ 处理超时，已重置。" 2>/dev/null || true
done

# ── Phase 2: Collect processable issues ──────────────────────────────────────
ISSUES_JSON=$(python3 << 'PYEOF'
import subprocess, json
def gh_issues():
    cmd = ["gh", "issue", "list", "--state", "open", "--json", "number,title,body,labels", "--limit", "20"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return json.loads(out) if out.strip() else []
    except: return []
result = []
seen = set()
for issue in gh_issues():
    num = issue["number"]
    labels = [l["name"] for l in issue.get("labels", [])]
    ai_labels = [l for l in labels if l.startswith("ai-")]
    if num not in seen and (not ai_labels or "ai-failed" in labels):
        seen.add(num)
        result.append({"number": num, "title": issue.get("title", ""), "body": issue.get("body", "")})
print(json.dumps(result, ensure_ascii=False))
PYEOF
)

COUNT=$(echo "$ISSUES_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$COUNT" -eq 0 ]; then
    log "No issues to process"
    exit 0
fi

log "Found $COUNT issue(s) to process"

# ── Phase 3: Process each issue ──────────────────────────────────────────────
PROCESSED=0
echo "$ISSUES_JSON" | python3 -c "
import sys, json
for issue in json.load(sys.stdin):
    print(f\"{issue['number']}|{issue['title']}|{issue['body']}\")
" 2>/dev/null | while IFS='|' read NUM TITLE BODY; do
    if [ $PROCESSED -ge $MAX_ISSUES ]; then break; fi
    PROCESSED=$((PROCESSED + 1))

    log "=== Processing #$NUM: $TITLE ==="

    # Mark processing
    gh issue edit "$NUM" --add-label "ai-processing" 2>/dev/null
    gh issue edit "$NUM" --remove-label "ai-failed" 2>/dev/null || true
    gh issue comment "$NUM" --body "🤖 AI 自动处理已启动" 2>/dev/null

    # Save pre-commit for rollback
    PRE_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")

    # AI fix via delegate_task (output to file for reliability)
    FIX_RESULT_FILE="/tmp/issue-${NUM}-fix-result.txt"
    log "Running AI fix..."

    # Use hermes delegate command if available, otherwise use python
    python3 << PYEOF > "$FIX_RESULT_FILE" 2>&1
import subprocess, json

# For now, we output a placeholder - the actual fix is done by the cron agent
# This script handles the mechanical parts, the agent does delegate_task
print("NEEDS_DELEGATE")
print(f"ISSUE_NUM={NUM}")
print(f"ISSUE_TITLE={TITLE}")
PYEOF

    # Read fix result
    FIX_RESULT=$(cat "$FIX_RESULT_FILE" 2>/dev/null || echo "ERROR")
    
    # If the script says NEEDS_DELEGATE, we can't do it from bash alone
    # The cron agent will handle this
    echo "DELEGATE_NEEDED|$NUM|$TITLE|$BODY"
done
