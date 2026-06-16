#!/usr/bin/env bash
# Pre-collection script for issue poller
# Outputs: one line per issue "NUMBER|TITLE|BODY"
# Empty output = nothing to process

set -uo pipefail
cd "$HOME/TollAuditExpress"

# Recover stuck issues
gh issue list --state open --label "ai-processing" \
    --json number,updatedAt --limit 20 \
    --jq ".[] | select(
        ((now - (.updatedAt | sub(\"\\+[0-9:]+\"; \"Z\") | strptime(\"%Y-%m-%dT%H:%M:%SZ\") | mktime)) / 60) > 10
    ) | .number" 2>/dev/null | while read NUM; do
    [ -z "$NUM" ] && continue
    gh issue edit "$NUM" --remove-label "ai-processing" --add-label "ai-failed" 2>/dev/null || true
    gh issue comment "$NUM" --body "⚠️ 处理超时，已重置。" 2>/dev/null || true
done

# Output processable issues
python3 << 'PYEOF'
import subprocess, json
def gh_issues():
    try:
        out = subprocess.check_output(["gh","issue","list","--state","open","--json","number,title,body,labels","--limit","20"], stderr=subprocess.DEVNULL, text=True)
        return json.loads(out) if out.strip() else []
    except: return []
for issue in gh_issues():
    num = issue["number"]
    labels = [l["name"] for l in issue.get("labels", [])]
    ai_labels = [l for l in labels if l.startswith("ai-")]
    if not ai_labels or "ai-failed" in labels:
        body = issue.get("body","").replace("\n"," ")
        print(f"{num}|{issue.get('title','')}|{body[:200]}")
PYEOF
