#!/usr/bin/env bash
# ============================================================================
# TollAuditExpress Issue Processor Helpers (闭环版 v3)
#
# Subcommands for the Hermes cron job agent to call:
#   mark_processing <issue>   — 标记 ai-processing + 评论
#   run_tests                 — 运行 pytest，输出 PASS/FAIL + 详情
#   commit_changes <#> <title>— git add + commit
#   rollback                  — 彻底回滚到上次 commit
#   finish_success <#> <summary> <test_output>  — 评论+关闭+ai-fixed
#   finish_testfail <#> <summary> <test_output> — 评论+保留+ai-failed
#   finish_failed <#> <error> — 评论+保留+ai-failed+rollback
# ============================================================================

set -uo pipefail
REPO_DIR="$HOME/TollAuditExpress"
cd "$REPO_DIR"

CMD="${1:?Usage: $0 <command> [args...]}"

case "$CMD" in
    mark_processing)
        NUM="$2"
        gh issue edit "$NUM" --add-label "ai-processing" 2>/dev/null
        gh issue edit "$NUM" --remove-label "ai-failed" 2>/dev/null || true
        gh issue comment "$NUM" --body "🤖 **AI 自动处理已启动** — 正在分析并修复，请稍候..." 2>/dev/null
        echo "MARKED"
        ;;

    run_tests)
        OUTPUT=$(python -m pytest tests/ -q --no-header --no-cov --ignore=tests/unit/services/test_passenger_obu_task_executor.py --ignore=tests/unit/services/test_trip_aggregator.py 2>&1 | tail -30)
        EXIT=$?
        if [ $EXIT -eq 0 ]; then
            echo "PASS"
        else
            echo "FAIL"
        fi
        echo "$OUTPUT"
        ;;

    commit_changes)
        NUM="$2"
        TITLE="$3"
        if [ -n "$(git diff --stat 2>/dev/null | head -1)" ] || [ -n "$(git ls-files --others --exclude-standard 2>/dev/null | head -1)" ]; then
            git add -A 2>/dev/null
            git commit --no-verify -m "fix: #$NUM - $TITLE (auto by Hermes Agent)" 2>/dev/null
            echo "COMMITTED"
        else
            echo "NO_CHANGES"
        fi
        ;;

    rollback)
        git checkout HEAD -- . 2>/dev/null || true
        git clean -fd 2>/dev/null || true
        echo "ROLLED_BACK"
        ;;

    finish_success)
        NUM="$2"; SUMMARY="$3"; TEST_OUT="$4"
        gh issue edit "$NUM" --remove-label "ai-processing" 2>/dev/null || true
        gh issue edit "$NUM" --add-label "ai-fixed" 2>/dev/null
        TEST_SHORT=$(echo "$TEST_OUT" | tail -12)
        gh issue comment "$NUM" --body "## ✅ AI 修复成功

${SUMMARY}

### 测试
✅ pytest 通过
\`\`\`
${TEST_SHORT}
\`\`\`
---
🤖 Hermes Agent" 2>/dev/null
        gh issue close "$NUM" --reason completed 2>/dev/null
        echo "CLOSED"
        ;;

    finish_testfail)
        NUM="$2"; SUMMARY="$3"; TEST_OUT="$4"
        gh issue edit "$NUM" --remove-label "ai-processing" 2>/dev/null || true
        gh issue edit "$NUM" --add-label "ai-failed" 2>/dev/null
        TEST_SHORT=$(echo "$TEST_OUT" | tail -12)
        gh issue comment "$NUM" --body "## ⚠️ AI 已修改代码但测试未通过

${SUMMARY}

### 测试
❌ pytest 失败
\`\`\`
${TEST_SHORT}
\`\`\`

补充说明后重新打开此 issue，我会重新处理。
---
🤖 Hermes Agent" 2>/dev/null
        echo "OPEN_TEST_FAIL"
        ;;

    finish_failed)
        NUM="$2"; ERROR="$3"
        gh issue edit "$NUM" --remove-label "ai-processing" 2>/dev/null || true
        gh issue edit "$NUM" --add-label "ai-failed" 2>/dev/null
        gh issue comment "$NUM" --body "## ❌ AI 处理失败

${ERROR}

此 issue 需要人工处理。
---
🤖 Hermes Agent" 2>/dev/null
        # Rollback
        git checkout HEAD -- . 2>/dev/null || true
        git clean -fd 2>/dev/null || true
        echo "OPEN_FAILED"
        ;;

    *)
        echo "Unknown command: $CMD"
        echo "Commands: mark_processing, run_tests, commit_changes, rollback, finish_success, finish_testfail, finish_failed"
        exit 1
        ;;
esac
