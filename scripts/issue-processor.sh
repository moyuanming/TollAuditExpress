#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Processor (Pre/Post hooks for Hermes agent)
# 
# These are helper functions called by the Hermes cron job agent.
# The actual code fixing is done by Hermes delegate_task subagent.
# ============================================================================

REPO_DIR="$HOME/TollAuditExpress"

# Mark an issue as being processed
mark_processing() {
    local issue_num="$1"
    cd "$REPO_DIR"
    gh issue edit "$issue_num" --add-label "ai-processing" 2>/dev/null
    gh issue comment "$issue_num" --body "🤖 **AI 自动处理已启动**

正在分析此 issue 并尝试修复，请稍候..." 2>/dev/null
}

# Comment result and close/keep-open issue
finish_issue() {
    local issue_num="$1"
    local success="$2"      # "yes" or "no"
    local test_passed="$3"  # "yes" or "no"
    local summary="$4"      # Brief summary of what was done
    local test_output="$5"  # Test output (truncated)

    cd "$REPO_DIR"
    gh issue edit "$issue_num" --remove-label "ai-processing" 2>/dev/null || true

    # Truncate test output
    test_output_short=$(echo "$test_output" | tail -20)

    if [ "$success" = "yes" ] && [ "$test_passed" = "yes" ]; then
        gh issue edit "$issue_num" --add-label "ai-fixed" 2>/dev/null
        gh issue comment "$issue_num" --body "## ✅ AI 修复成功

### 修复内容
$summary

### 测试结果
✅ 测试通过

\`\`\`
$test_output_short
\`\`\`

---
🤖 由 Hermes Agent 自动处理" 2>/dev/null
        gh issue close "$issue_num" --reason completed 2>/dev/null
        echo "CLOSED"

    elif [ "$success" = "yes" ] && [ "$test_passed" = "no" ]; then
        gh issue edit "$issue_num" --add-label "ai-failed" 2>/dev/null
        gh issue comment "$issue_num" --body "## ⚠️ AI 已修改代码，但测试未通过

### 修改内容
$summary

### 测试结果
❌ 测试失败

\`\`\`
$test_output_short
\`\`\`

请人工检查。你可以补充说明后重新打开此 issue，我会重新处理。

---
🤖 由 Hermes Agent 自动处理" 2>/dev/null
        echo "OPEN_TEST_FAIL"

    else
        gh issue edit "$issue_num" --add-label "ai-failed" 2>/dev/null
        gh issue comment "$issue_num" --body "## ❌ AI 处理失败

### 错误信息
$summary

此 issue 需要人工处理。

---
🤖 由 Hermes Agent 自动处理" 2>/dev/null
        # Revert any changes
        git -C "$REPO_DIR" checkout -- . 2>/dev/null || true
        git -C "$REPO_DIR" clean -fd 2>/dev/null || true
        echo "OPEN_FAILED"
    fi
}

# Run tests and return result
run_tests() {
    cd "$REPO_DIR/apps/api"
    local test_output=""
    local test_exit=0
    
    test_output=$(python -m pytest -x --tb=short -q 2>&1 | tail -30) || test_exit=$?
    
    if [ $test_exit -eq 0 ]; then
        echo "PASS"
    else
        echo "FAIL"
    fi
    echo "$test_output"
}

# Commit changes if any
commit_changes() {
    local issue_num="$1"
    local issue_title="$2"
    cd "$REPO_DIR"
    
    local changes
    changes=$(git diff --stat 2>/dev/null | head -5)
    local untracked
    untracked=$(git ls-files --others --exclude-standard 2>/dev/null | head -5)
    
    if [ -n "$changes" ] || [ -n "$untracked" ]; then
        git add -A
        git commit -m "fix: resolve issue #$issue_num - $issue_title

Auto-fixed by Hermes Agent issue processor.

Closes #$issue_num" 2>/dev/null || true
        echo "COMMITTED"
    else
        echo "NO_CHANGES"
    fi
}

# Dispatch based on command
case "${1:-}" in
    mark_processing)
        mark_processing "$2"
        ;;
    finish_issue)
        finish_issue "$2" "$3" "$4" "$5" "$6"
        ;;
    run_tests)
        run_tests
        ;;
    commit_changes)
        commit_changes "$2" "$3"
        ;;
    *)
        echo "Usage: $0 {mark_processing|finish_issue|run_tests|commit_changes} [args...]"
        exit 1
        ;;
esac
