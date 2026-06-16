#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Poller (闭环版)
#
# 输出: JSON 数组 [{number, title, body}, ...]
# 诊断信息输出到 stderr
# ============================================================================

set -uo pipefail
REPO_DIR="$HOME/TollAuditExpress"
STUCK_MINUTES="${1:-10}"
cd "$REPO_DIR"

# ── Phase 1: Recover stuck issues (ai-processing > N min) ───────────────────
gh issue list --state open --label "ai-processing" \
    --json number,updatedAt --limit 20 \
    --jq ".[] | select(
        ((now - (.updatedAt | sub(\"\\+[0-9:]+\"; \"Z\") | strptime(\"%Y-%m-%dT%H:%M:%SZ\") | mktime)) / 60) > $STUCK_MINUTES
    ) | .number" 2>/dev/null | while read NUM; do
    echo "[RECOVER] Issue #$NUM stuck, resetting" >&2
    gh issue edit "$NUM" --remove-label "ai-processing" --add-label "ai-failed" 2>/dev/null || true
    gh issue comment "$NUM" --body "⚠️ 处理超时，已重置。将在下次轮询中重新处理。" 2>/dev/null || true
done

# ── Phase 2+3: Collect processable issues ───────────────────────────────────
# New issues (no ai-* labels) + failed issues (ai-failed + open)
# Use Python to merge and deduplicate

python3 << 'PYEOF'
import subprocess, json

def gh_issues(extra_args=[]):
    cmd = ["gh", "issue", "list", "--state", "open", "--json", "number,title,body,labels", "--limit", "20"] + extra_args
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return json.loads(out) if out.strip() else []
    except:
        return []

all_issues = gh_issues()  # all open issues
seen = set()
result = []

for issue in all_issues:
    num = issue["number"]
    labels = [l["name"] for l in issue.get("labels", [])]
    ai_labels = [l for l in labels if l.startswith("ai-")]

    # Process if: no ai-* labels (new) OR has ai-failed (retry)
    if num not in seen and (not ai_labels or "ai-failed" in labels):
        seen.add(num)
        result.append({"number": num, "title": issue.get("title", ""), "body": issue.get("body", "")})

print(json.dumps(result, ensure_ascii=False))
PYEOF
