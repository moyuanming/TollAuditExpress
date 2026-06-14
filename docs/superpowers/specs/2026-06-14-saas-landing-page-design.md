# TollAuditExpress 营销落地页 — 设计

**日期:** 2026-06-14
**状态:** Draft,待用户 review
**作者:** brainstorm session (Claude + user)

---

## 1. 目标与受众

为 TollAuditExpress(高速公路收费稽核系统)新增一个**对外的营销落地页**,面向**高速公路运营单位的采购 / 技术决策者**(信息中心、稽核部门负责人)。主转化动作:申请免费试用 → 后端入库。

放在现有 monorepo 内的 `apps/web` 中,与原内部 dashboard 共仓共部署,但**路由分离**——`/` 是 public landing,`/app/*` 是受 AuthGuard 保护的内部系统。

---

## 2. 路由调整

| 路径 | 权限 | 内容 |
|------|------|------|
| `/` | public | 新增 **Landing 页**(本设计主体) |
| `/app` | auth | 原 Dashboard,改名 `AppHome` |
| `/app/trips` | auth | 原 TripQuery |
| `/app/vehicles` | auth | 原 VehicleQuery |
| `/app/suspects` | auth | 原 SuspectList |
| `/app/stats` | auth | 原 Statistics |
| `/app/tasks` | auth | 原 TaskManager |
| `/app/rules` | auth | 原 RuleStudio |
| `/redirect` | public | 原 Redirect(不变) |
| `/app/login` | public | 跳转到后端配置的 `loginUrl`(外部 OIDC);由 AuthGuard 触发 |

**登录机制说明**:本项目不内置登录页,`AuthGuard` 收到未鉴权请求时直接 `window.location.replace(loginUrl)`(配置项,后端返回)。落地页的「登录后台」按钮直接打开 `/app`(被 AuthGuard 拦下后由现有逻辑跳 OIDC),不需要新写代码。

**老路径兼容**:`/trips`、`/vehicles` 等老链接 → 统一 302 重定向到 `/app/trips` 等,保持外部引用不破。

**App.jsx 调整**:
- 内部 routes 从 `/` 改到 `/app/*`
- `AuthGuard` 包裹 `/app/*` 子树
- `<Landing />` 挂到 `/`,置于 AuthGuard 之外

---

## 3. 页面 Section 设计

整体视觉风格:**现代 SaaS 风**(浅色 + 紫蓝渐变,白底卡片,圆角 8–12px,字号 14–48px,Inter / 思源黑体)。

### 3.1 Hero(首屏)
- **nav**:`稽 · 高速公路收费稽核系统` brand 在左;右 4 个 anchor(能力 / 架构 / 数据 / 联系)+「登录后台」按钮(已登录显示用户名,未登录显示「登录后台」)
- **eyebrow**:`TollAudit · 高速公路 AI 稽核`
- **H1**:**让每一笔通行费,都不再流失**
- **副标题**:基于双 AI 视觉模型,毫秒级识别 8 类常见逃费行为,准确率 99.2%,服务高速运营单位本地化部署。
- **CTA 主**:**申请免费试用 →**(滚动到 #contact)
- **CTA 次**:下载技术白皮书(占位链接,后续替换)
- **右侧图**:`稽` 字 logo + 路网插画占位

### 3.2 8 类检测能力区(4×2 网格)
- **标题**:**8 类逃费行为,AI 自动识别**
- **副标题**:覆盖主流高速场景,持续扩展
- 8 张卡(徽章 01–08 + 名称 + 一行说明):
  1. 货车套用客车 OBU — 入口车型 vs 视觉识别
  2. 出入口车辆不一致 — 车牌/车型/车纹多维比对
  3. 门架路径异常 — 序列与拓扑不符
  4. 车型降档 — 交易记客,识别为货
  5. 同车牌多 OBU — 历史绑定异常
  6. OBU 多车绑定 — OBU 短时绑多车
  7. OBU 屏蔽 — 无 OBU 但有出口图
  8. 车牌 OBU 历史异常 — 历史关系异常

### 3.3 架构 / 部署区(三栏特性卡)
- **标题**:**为高速运营方而生 · 安全可控**
- **副标题**:支持本地化部署,数据不出域
- 三张卡:🏢 本地化部署 / 🔌 源库直连 / 🤖 AI 模型分离

### 3.4 数据证据区(4 数字横排,浅色背景)
- `8` 逃费类型
- `99.2%` 识别准确率
- `<200ms` 单次识别
- `3 机` 部署拓扑
- 小字注脚:数据来源于内部测试环境,实际值以部署报告为准

### 3.5 底部 CTA(表单,#contact)
- **标题**:**申请免费试用**
- **副标题**:填写后我们 1 个工作日内联系您
- 字段(必填项 *):姓名 *、联系电话 *、单位名称 *、邮箱、备注(0–500)
- 提交按钮:**提交申请**
- 成功 → 替换为「提交成功,我们会尽快联系您 ✓」+ 再次提交链接
- 失败 → toast + 行内错误

---

## 4. 数据流与状态管理

### 4.1 表单提交流

```
[LandingCTA.jsx]
  ├─ 客户端校验 (必填 / 电话 ^1[3-9]\d{9}$ / 邮箱 EmailStr)
  ├─ 提交中: button disabled + 文案「提交中...」
  ├─ 200/201 → 切换 success 视图
  ├─ 422 → errors[] 按字段名映射到行内提示
  └─ 5xx / 网络错误 → toast「提交失败,请稍后重试」

POST /api/landing/leads  (FastAPI,无 auth)
  body → LandingLeadCreate (Pydantic 严格校验)
  └─ LandingRepository.insert()  → ods_AI_DB.landing_leads
     字段: id, name, phone, org, email?, message?,
           source='landing-page', ip, ua, created_at
  201 Created { id, created_at }
```

### 4.2 状态归属

| 状态 | 范围 | 实现 |
|------|------|------|
| nav 当前 section 高亮 | LandingNav | IntersectionObserver,无第三方 |
| 表单字段值 | LandingCTA | useState 受控 |
| 提交状态 idle/submitting/success/error | LandingCTA | useState status |
| 行内错误 | LandingCTA | useState 按字段存 |
| 锚点平滑滚动 | 全局 | CSS `scroll-behavior: smooth` + `scrollIntoView` |

### 4.3 限流
- 同一 IP 1 分钟内最多 5 次提交(简单内存 dict;不引入 Redis)

### 4.4 错误处理
- 422 错误细节按字段名匹配,行内红字提示
- DB 故障 → 500 + 后端日志,前端统一 toast
- 后端使用参数化 SQL(已沿用现有 pymysql 模式,SQL 注入由 Pydantic 长度 + 格式校验 + 参数化语句共同防御)

### 4.5 复用与不复用
- **复用**:Vite/React/Router 配置、AuthContext(只读 isAuthenticated)、axios 拦截器
- **不复用**:App.jsx 内部 nav(改名为 AppNav)、dashboard 表格/筛选组件(landing 不需要)

---

## 5. 文件清单(预计 14 个新文件 + 3 个修改)

### 新增
```
apps/web/src/pages/Landing/
  Landing.jsx, Landing.css
  sections/Hero.jsx, Hero.css
  sections/Capabilities.jsx, Capabilities.css
  sections/Architecture.jsx, Architecture.css
  sections/Stats.jsx, Stats.css
  sections/CTA.jsx, CTA.css
apps/web/src/components/LandingNav.jsx, LandingNav.css
apps/web/src/api/landing.js
apps/api/routers/landing.py
apps/api/schemas/landing.py
apps/api/database/repositories/landing_repository.py
tests/web/test_landing_form.test.jsx
tests/web/test_routing.test.jsx
tests/api/test_landing_routes.py
```

### 修改
- `apps/web/src/App.jsx` — 路由改造(Landing 提到 `/`、原页面移 `/app/*`、AuthGuard 边界调整)
- `apps/api/main.py` — 注册 landing router
- `packages/contracts/types/schemas.py` — 追加 `LandingLead` 模型(与前端 TS 类型同步)
- `docs/USER_MANUAL.md` — 增加「公开落地页」章节(可选)

---

## 6. 测试策略

### 前端(Vitest + React Testing Library)
- `tests/web/test_landing_form.test.jsx`
  - 必填校验、电话 / 邮箱格式校验
  - 200 → 成功视图;422 → 行内错误;5xx → toast
  - 提交中按钮 disabled + 文案变更
- `tests/web/test_routing.test.jsx`
  - `/` public,未登录看到 Landing
  - `/app` auth,未登录跳登录页
  - 老路径 `/trips` 等重定向到 `/app/trips`

### 后端
- `tests/api/test_landing_routes.py`
  - 合法 body → 201 + DB 行存在
  - 缺字段 / 格式错 → 422
  - 限流:1 分钟内第 6 次 → 429
  - DB mock 故障 → 500
  - GET /api/landing/leads 无 token → 401,带 token → 200 分页
  - SQL 注入 payload → 拒绝(DB 表完好)

### 验收清单(PR 前)
- [ ] 4 个 section 在 1280 / 768 / 375 视口下布局正常
- [ ] 浏览器控制台无 error / warn
- [ ] 表单提交 → DB 行存在 → GET 后台拉到
- [ ] `/` 未登录/已登录都正常显示
- [ ] 老内部链接加 `/app` 前缀后功能不变

### 不测
- 视觉像素级(走人工或 Playwright 抽查)
- 真实邮件发送(本设计不实现)

---

## 7. 范围外(明确不做)

- Google Analytics / 百度统计
- A/B testing 框架
- i18n(纯中文)
- SEO 高级优化(只做基础 `<title>` / `<meta description>`)
- 邮件发送 / 短信通知
- 管理后台 UI(用 GET API 临时查 DB,或后续单独做)

---

## 8. 风险与备注

1. **数字真实性**:99.2% / <200ms / 8 类 / 3 机 在公开 docs 中只有「8 类」「3 机」是事实,99.2% 与 <200ms 是推断的占位。已在页面加注脚说明,后续需用真实数字替换。
2. **数据库迁移**:`landing_leads` 是新表,需要在 `ods_AI_DB` 上 DDL。建议先在测试库建,验证后由部署脚本应用。
3. **老链接兼容**:已规划 302 重定向,不会破外部引用。
4. **AuthGuard 改造风险**:App.jsx 路由调整影响所有内部页面。需回归测试 dashboard 全部 7 个内部页面。
