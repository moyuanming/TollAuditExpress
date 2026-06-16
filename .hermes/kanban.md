# TollAuditExpress 开发看板

## 🔴 Critical — 阻塞线上
- [ ] [无 CI/CD 流水线] GitHub Actions 已配置，需推送到远程仓库后激活
- [ ] [Ruff 告警 150+] 运行 `ruff check --fix` 自动修复大部分，剩余需手动处理

## 🟡 In Progress — 进行中
- [ ] 客车 OBU 监测功能完善（passenger_obu_detector + 前端页面）
- [ ] Doris 行程查询优化（doris_trip_query.py 有改动未验证）
- [ ] 图表组件开发（DailyScanBar / LineTrend / PieDistribution 已创建）

## 🟢 Backlog — 待排期
- [ ] E2E 测试补充（当前仅 health + schemas 两个）
- [ ] 前端 ESLint 配置（当前无 .eslintrc）
- [ ] 前端 TypeScript 迁移（.jsx → .tsx）
- [ ] packages/contracts 完善（当前仅有空 types 目录）
- [ ] API 文档完善（FastAPI 自动文档 + 业务说明）
- [ ] 性能监控（APM / 日志聚合）
- [ ] Doris DDL 版本管理（当前 migration 文件无版本控制表）

## ✅ Done — 已完成
- [x] 工作区整理（.gitignore + 清理缓存 + 提交）
- [x] 分支策略建立（develop 分支 + 文档）
- [x] CLAUDE.md 常用命令补齐
- [x] CI/CD 流水线配置（.github/workflows/ci.yml）
- [x] 质量门禁（ruff.toml + pre-commit hooks）
- [x] Landing Page 开发
- [x] 前端路由拆分（Landing / /app/*）
- [x] Vitest + React Testing Library 配置
