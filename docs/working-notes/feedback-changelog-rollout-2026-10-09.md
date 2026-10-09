# 反馈与更新日志闭环：调研结论与演进方案

> 2026-10-09 调研产出 · 里程碑 #16「反馈与更新日志闭环 Feedback & Changelog」
> 关联卡：#1996（更新日志链路）· #1997（app 接入 widget）· #2000（外链与SSO 后续）

## 一、现状盘点（实测，非推测）

### 1.1 已有的（比预期多）

| 资产 | 状态 | 证据 |
|------|------|------|
| FeedLog 自部署站| ✅ 线上 200 | `feedback.duoduobei.com` |
| widget 服务端配置 | ✅ 可匿名读 | `/api/widget/config` 返回 `enabled:true` |
| roadmap | ✅ 8 张卡片 | `/roadmap` 有planned/in-progress/completed |
| 桥接脚本 | ✅ 878 行，三通道 | `scripts/bridge/feedlog_bridge.py` |
| 桥接工作流 | ✅ 在跑 | 2026-10-09 10:13 schedule success |
| FeedLog→GitHub 定时同步 | ✅ 每 3 小时 | 同上 |
| GitHub Issue→FeedLog 状态回写 | ✅ | 今日多次 issues 事件 success |
| Issue 编辑回灌 | ✅ 每日一次 | `bridge-edited-sync.yml` 每日 success |
| fork 中文/品牌/部署适配 | ✅ 领先上游 194 文件 | `/d/codes/ddb-feedback` vs `linkcraftstudio/feedlog` |

### 1.2 缺的（本次要补的）

| 缺口 | 根因 |
|------|------|
| **更新日志是空的** | `gh release list` 为空 → `on: release: published` 从未触发 → 通道 3 空转。**代码没问题** |
| **app 未接 widget** | 前端零 `@feedlog/widget` 引用 |
| **游客不能提交** | `/api/widget/config` 返回 `allowGuest:false` |
| 无发版流程 | 无 tag（除孤 `v0.1`）、无 Release、无发版文档 |
| changelog 无分类 | `create_changelog_entry()` 硬编码 `categories="[]"` |

## 二、关键结论：widget 要不要后端

**要，但只要一个 token 端点；且这个端点不该在主站。**

官方 widget 有两条集成路径：

| 模式 | 后端需求 | 适用|
|------|---------|------|
| 游客模式 | **零后端**，`createWidget({baseUrl})` 纯前端 | 先跑通链路 ✅ 本卡采用 |
| SSO 模式 | 需服务端签 HS256 JWT（`email`+`exp` 必填，≤24h） | 后续卡 |

`allowGuest:false` 意味着游客模式当前不可用，必须先在 workspace 开启。

### 为什么不在主站做

主站 `duoduobei.com` 是独立仓/静态资产，无用户登录态、无页面上下文，读不到"当前用户"。而：

- app（账本精灵）有 Supabase 登录态 + 当前路由上下文；
- FeedLog widget **自动把页面 path/title/meta 喂给 Agent**，SPA 路由变化无需额外配置。

所以反馈装在 app，天然能收到「用户在哪个功能点提的反馈」，信息密度高得多。

## 三、方案（分三层，按依赖排序）

### L1 更新日志（#1996）— 零开发，最高性价比

```
dev 合入 → 打 tag → gh release create → release:published 事件
        → bridge-feedback.yml 触发 → create_changelog_entry() 直连 Neon 写 changelog 表
        → 公开 /changelog 页面出现条目
```

**唯一障碍：从来没发过 Release。** 补发即可。

配套：发版流程文档 + 脚本 + 历史汇总条目 + categories 推导（Conventional Commits → New/Improved/Fixed）。

⚠️ **未决：版本号口径。** 现状矛盾：`v0.1` tag vs `package.json` 6.2.0。建议用 `v0.1.0` 重新对齐（M0 未到，对外无正式发布）。

### L2 app 接入 widget（#1997）— 小前端改动

开`allowPost` → `pnpm add @feedlog/widget` → 客户端启动处 `createWidget()` → 真机走查。

零后端。已知代价：反馈匿名，无法关联登录用户（留给 SSO 卡）。

### L3 外链 + SSO 后续（#2000）

- 主站 / docs 站各放一个指向 `feedback.duoduobei.com` 的按钮（纯静态，零后端）
- SSO：Flask 加 `/api/feedlog-token`。**与 #1029（父域 cookie SSO）是两件事**，别混

## 四、里程碑决策

**新建 #16，不挂 M0。** 理由：M0 Launch 是部署形态/域名（#894），反馈闭环是产品侧基础设施，两者并行推进、互不阻塞；混在一起会让 M0 失焦。

## 五、待验证/未知（不猜测）

1. `allowPost` 单独开启时游客能否投票 —— 官方文档说三开关独立，**实测**才知
2. `zIndex: 40` 是否与 pure-admin + Element Plus 浮层层叠冲突 —— 推断不算数
3. `create_changelog_entry()` 声称幂等，但每次用 `uuid4()[:8]` 生成新 slug，**幂等判断可能实际失效**（同 Release 重复触发会插两条）。需实证
4. `categories` 字段：当前传字符串 `"[]"`，而 schema 疑为 JSON 数组 —— 改造前用真实 schema 验证，别照抄现有代码的错
5. 品牌色冲突：working-notes 写 `#10B981`（绿），线上实际 `#E34F38`（红橙）—— **哪个是准的待确认**

## 六、能做到什么程度（务实回答）

用户问「做不到完美的话能做到什么程度」—— 分层给出：

| 阶段 | 能做到 | 代价 |
|------|--------|------|
| **当天** | 发首个 Release → 更新日志立刻有内容；开`allowPost` → app 立刻能收反馈 | 几十分钟配置 |
| **一周内** | widget 在app 亮/暗主题正常、窄屏不炸；发版流程文档化、脚本化 | 一个前端 PR |
| **一月内** | 主站/docs 外链；3–5 条真实更新日志；roadmap 有真实卡片在流转 | 零后端小活 |
| **想更perfect** | SSO 绑定用户身份 → 反馈可运营；AI 从反馈起草 changelog；categories 自动化 | 需Flask 端点 + workspace SSO secret |

**建议先走到「一周内」**，拿到真实反馈数据再决定要不要投入 SSO。反馈系统最大的坑不是功能缺失，是**建了没人用**——先有数据，再谈精细化。