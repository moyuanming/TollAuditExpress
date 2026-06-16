# Release Checklist — 2026-06-16

> 本次将 `develop` 分支(顶端 commit `f78c9b2`,领先 `origin/develop` 3 个 commit)发布到目标机 `root@10.11.1.40:8080`,使用 `deploy.sh full` 全链路模式。
> 配套文档:[feature-inventory.md](./feature-inventory.md)。

---

## 发布前检查(必做)

### 1. 代码状态

- [ ] `git status` 工作区 clean
- [ ] 当前在 `develop` 分支
- [ ] 顶端 3 个 commit:`f78c9b2`(验证自动修复闭环)、`d765de0`(README)、`82a7245`(健康检查)
- [ ] 顶端再往前 2 个:`b26589c`(services 单测 82%)、`639199f`(基础设施)

### 2. 环境与凭据

- [ ] `deploy.config.env` 存在且包含:`BUILD_SERVER=root@159.138.100.157`、`TARGET_SERVER=root@10.11.1.40`、`SERVICE_PORT=8080`、`SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"`
- [ ] 本地 SSH key 已添加到构建机和目标机 root 信任列表
- [ ] 本地 Docker 可用,`docker --version` 正常

### 3. 连接自检

```bash
bash scripts/check-conn.sh
# 预期:SSH 到构建机和目标机都通,远端 docker 可用,退出码 0
```

如果失败:
- 检查 `~/.ssh/config` / `~/.ssh/known_hosts`
- 检查目标机 8080 端口是否被其他容器占用:`ssh root@10.11.1.40 "lsof -i:8080"`

---

## 全量测试(必做,失败立即停)

### 1. 后端静态检查

```bash
ruff check apps/api/ tests/
ruff format --check apps/api/ tests/
```

- 预期:可能存在历史告警,记录数量;**仅检查本次新增 error**(如有)。
- 若有新增 error → 立即修复后再继续。

### 2. 后端 pytest

```bash
pytest tests/unit/ tests/api/ -v --tb=short
pytest tests/e2e/ -v --tb=short
pytest --cov=apps/api --cov-report=term-missing --cov-fail-under=60
```

- 预期:全部 pass,覆盖率 ≥ 60%(历史 82%)
- 若失败 → 看 `--tb=short` 定位,优先修测试和生产 bug

### 3. 前端测试与构建

```bash
cd apps/web
npm ci --legacy-peer-deps
npm test           # vitest run,全绿
npm run build      # 验证 dist/ 生成
cd ..
```

- 预期:2 个测试文件全过,`dist/` 重新生成

### 4. 关键风险点核验

- [ ] `apps/api/database/connection.py`(旧 SQLite):仅被 `tests/conftest.py` + `migrate_sqlite_to_doris.py` 引用,生产 import 已切到 `doris_connection.py`
- [ ] `AUTH_ENABLED=false` 默认走 API_KEY,与目标机现状一致
- [ ] `data/audit.db`(54 MB):保留作迁移源,不动

---

## 推送与 CI 激活

```bash
git push origin develop
```

- 预期:3 个 commit 推送到 `origin/develop`
- CI(`.github/workflows/ci.yml`)自动触发:`api-lint` + `api-test` + `web-test`(`docker-build` 仅 main 触发)
- 远端 CI 全绿作为额外保险层(本地测试已通过 + CI 也通过 = 双保险)

---

## 执行 deploy.sh full

```bash
bash deploy.sh full
```

内部流程(`deploy.sh:161-227`):
1. 前端 `npm run build`(`[1/7]` 前端构建)
2. SSH 到构建机,清理旧构建产物
3. 本地 `rsync -avz --delete` 同步代码(排除 `.git`、`node_modules`、`__pycache__` 等)
4. **本地 `pytest tests/ -m "not slow"` 跑全量测试**(已通过则秒过)
5. SSH 到构建机 `docker build` 构建镜像(多阶段:`node:18-slim` → `python:3.10-slim` → `appuser` 生产镜像)
6. `docker save | gzip` → 本地中转 → `scp` 到目标机(`deploy.sh:196` 注释的兼容性问题)
7. 目标机 `docker load` + `docker run -d --restart unless-stopped -p $SERVICE_PORT:8000` + 卷挂载 + `cleanup_orphan_containers`
8. 健康检查(30s 超时)

**预计耗时**:10-20 分钟,主要在第 5-6 步(镜像构建 + 大文件传输)。

**关键错误处理**:
- 第 4 步测试失败 → deploy.sh 立即 exit 1,不动镜像
- 第 5 步构建失败 → 看构建机 stderr(`docker build` 输出)
- 第 7 步容器启动失败 → `ssh root@10.11.1.40 "docker logs toll-audit-express --tail 200"`
- 第 8 步健康检查失败 → 容器仍会运行(只是健康检查失败),人工 `curl /api/health` 验证

---

## 发布后烟测(发布完成的判定)

依次执行,任一失败立即排查:

### 1. 容器状态

```bash
ssh root@10.11.1.40 "docker ps | grep toll-audit-express"
ssh root@10.11.1.40 "docker inspect --format='{{.State.Health.Status}}' toll-audit-express"
# 预期:容器 Running,Health.Status=healthy
```

### 2. 健康端点

```bash
curl -sf http://10.11.1.40:8080/api/health | jq
# 预期:{"status":"ok"}

curl -sf http://10.11.1.40:8080/api/health/doris | jq
# 预期:status=ok,target_db.connected=true,5 张表行数都 ≥0,source_db.connected=true
```

### 3. 关键 API 烟测

```bash
# Stats 概览(无需鉴权走匿名 200 或 401 都算端点可达)
curl -sf http://10.11.1.40:8080/api/audit/stats/overview | jq '.data | keys'
# 预期:返回 keys 数组

# 行程列表(带 API Key)
curl -sf -H "X-API-Key: $API_KEY" 'http://10.11.1.40:8080/api/audit/trips?limit=1' | jq '.data | length'
# 预期:.data 数组长度 0 或 1

# 可疑记录列表
curl -sf -H "X-API-Key: $API_KEY" 'http://10.11.1.40:8080/api/audit/suspects?limit=1' | jq '.data | length'
```

> 注:`$API_KEY` 是发布环境配置的 API_KEY;若目标机 `.env` 是新版,可 `ssh root@10.11.1.40 "grep API_KEY /path/to/.env"` 查看。

### 4. 前端可达

```bash
curl -sf http://10.11.1.40:8080/ | head -c 200
# 预期:返回 HTML 含 <div id="root">

curl -sf -I http://10.11.1.40:8080/assets/ | head -1
# 预期:静态资源目录可访问(404 也算端口正常,仅看响应)
```

### 5. 容器日志无异常

```bash
ssh root@10.11.1.40 "docker logs toll-audit-express --tail 100"
# 预期:无 traceback,无反复出现的 Exception
```

---

## 回滚方案

如果发布后烟测任一步失败,按严重程度选:

### 轻度(部分 API 异常)

不需回滚镜像,在容器内调试:

```bash
ssh root@10.11.1.40
docker exec -it toll-audit-express bash
# 在容器内 curl / 日志排查
```

### 中度(容器起不来 / 健康检查永远 unhealthy)

```bash
# 1. 停当前容器
ssh root@10.11.1.40 "docker stop toll-audit-express && docker rm toll-audit-express"

# 2. 看历史镜像,选上一个 tag 启动(假设上一个 tag 名为 toll-audit-express:previous)
ssh root@10.11.1.40 "docker images | grep toll-audit-express"
ssh root@10.11.1.40 "docker run -d --name toll-audit-express --restart unless-stopped -p 8080:8000 \
  -v /path/to/.env:/app/.env:ro \
  -v /path/to/data:/app/apps/api/data \
  -v /path/to/logs:/app/logs \
  toll-audit-express:previous"
```

### 重度(数据库/配置破坏)

1. 先用 `scripts/issue-processor.sh rollback` 回滚**工作区**(只回滚本机,不影响已发布镜像)
2. 调查根因(看容器日志、Doris 健康状态、`.env` 是否被覆盖)
3. 在 `develop` 上修复并出新 commit
4. 重新执行本 checklist

---

## 交付物清单

完成本次发布后,在仓库内产生/确认以下文件:

- [x] `docs/feature-inventory.md`(本次新增,功能清单)
- [x] `docs/release-checklist-2026-06-16.md`(本文档)
- [x] `develop` 分支多 1 个 commit(`docs: add feature-inventory + release-checklist`)
- [x] `origin/develop` 与本地 `develop` 同步
- [x] 目标机 `toll-audit-express` 容器跑通 `/api/health`

---

## 沟通

- 发布过程中任何异常(测试失败 / 构建失败 / 部署失败)立即告知,不静默重试超过 2 次。
- 完成后输出发布报告:版本(commit sha)、目标机容器 ID、烟测结果摘要、下次发布注意点。
