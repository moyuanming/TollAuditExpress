# TollAuditExpress 分支策略

## 分支模型

采用简化的 Git Flow：

| 分支 | 用途 | 保护 | 部署 |
|------|------|------|------|
| `main` | 生产就绪代码 | ✅ 保护分支 | 自动部署到生产 |
| `develop` | 开发集成分支 | ✅ 保护分支 | 部署到开发/测试环境 |
| `feat/<name>` | 功能分支 | ❌ | — |
| `fix/<name>` | 修复分支 | ❌ | — |
| `refactor/<name>` | 重构分支 | ❌ | — |

## 命名规范

```
feat/passenger-obu-monitor    # 新功能
fix/doris-connection-timeout   # Bug 修复
refactor/trip-query-service    # 重构
chore/update-dependencies      # 杂项
```

## 工作流

1. 从 `develop` 创建功能分支：`git checkout -b feat/xxx develop`
2. 开发完成后，在 GitHub 上创建 PR → `develop`
3. PR 需通过 CI 检查 + 至少 1 人 review
4. 合并后删除功能分支
5. `develop` 测试通过后，创建 PR → `main` 发版

## Commit 规范

使用 Conventional Commits：

```
feat(api): 添加客车 OBU 监测接口
fix(web): 修复时间线组件空数据崩溃
refactor(services): 拆分 trip_aggregator 为独立模块
chore(deps): 升级 fastapi 到 0.110
test(api): 补充 doris_trip_query 单测
docs: 更新部署文档
```

## 发版流程

1. `develop` 冻结 → 创建 PR `develop` → `main`
2. 合并后在 `main` 上打 tag：`v1.x.x`
3. CI 自动构建 Docker 镜像并推送
