# 幽灵重复告警接入对账工作台（域 D 前端，2026-10-16）

关联：CNB duoduobei/fundmate#477 / GitHub https://github.com/imoyao/fundmate/issues/2151 （域 D 后端为 PR1 / CNB duoduobei/fundmate#486）。

## 做了什么

| 面 | 内容 |
| :-- | :-- |
| API | `api/reconciliation.ts` 新增域 D 五条端点的类型与调用（类型逐字段照抄后端，不二次推导） |
| Tab | `domainTabs.ts` 新增域 D，并抽出 `WorkbenchDomainKey = "A" \| "B" \| "C" \| "D"` |
| 组件 | 新增 `DomainDGhostTable.vue`（逐组卡片 + 组内明细 + 忽略/撤销 + 删一份） |
| 数据 | `useWorkbenchDomains.ts` 接入域 D 的加载 / 忽略 / 撤销 / 删除 |
| 寻址 | `index.vue` 的 `activeDomain` 与 `route.query.domain` 双向同步 |
| 横幅 | `GhostDuplicateBanner` 加「去对账工作台处理」跳转，关闭语义改为**本次会话** |

## 三个值得单独说的判断

### 1. 横幅换用 reconciliation 端点，不是「顺手」

横幅原先读 `/api/summary/ghost-duplicates/`，而该端点返回的是
**未减掉忽略项**的全量扫描（`scan_cross_ledger_duplicates` 直出）。
若横幅报「407 组」、点进域 D 只剩 401 组，用户第一眼就是数字对不上——
这正是 issue 里点名要避免的「新的困惑」。

故横幅改用 `GET /api/reconciliation/ghost-duplicates/`：同一份扫描，
但返回 `{groups（已减忽略）, ignored_count}`，与域 D 列表**同源同口径**。

代价：`/api/summary/ghost-duplicates/` 至此在**前端没有消费者**。
本次**不删**（它是 API 契约，且 AI 识别 / 报表类后续可能用），登记在 PR 描述里待判断。

### 2. dismiss 从「永久」改成「本次会话」，而不是「换一个 key 继续永久」

卡面写的修法是「localStorage key 必须带 family_id」。但只换 key 是**治了症状没治病**：
原代码 `onMounted` 命中 key 后**连请求都不发**，于是「关掉一次」在语义上等于
「这条告警从此不存在」——这才是「407 组只能关闭」的真因（关掉就再也看不到）。

现有域 D 提供真正的落点后，关闭就该退化为「这次先不看」：改用 `sessionStorage`，
刷新 / 重进即恢复检查。`family_id` 维度仍然加上（`ghost_dup_banner_dismissed:<fid>`），
但它是**次要修正**——主要修正是把「永久」改掉。

家庭 id 的来源有一处现实约束：前端**没有同步可用的 familyId**
（路由守卫只把展示名写进 localStorage，`MeResult` 里的 `family.id` 未被持久化）。
故靠 `GET /api/auth/me/` 惰性拉一次并模块内缓存。拿不到时退化为无后缀 key：
宁可「隔离失效」也不要「开关失效」——后者会让用户在异常态下被一条关不掉的横幅一直顶着。

### 3. 删除文案不说「保留真实的那一份」

后端 `transactions.source` 为 NULL 时**无法指出组里哪一份是权威的**，
所以文案是「保留你认为真实的那一笔，另一份删除」。做后端支撑不了的断言，
等于把用户的信任透支在一句 UI 文案上。

删除走 `DELETE /api/transactions/<id>/`（既有端点，会连带重算持仓），
故给了 `ElMessageBox` 二次确认——它是不可逆操作，且每一条都是用户自己录进来的真实数据。

## 已知边界（未做，不在本卡范围）

- **§6.5 的跨域已忽略清单**（`GET /api/reconciliation/ignored/` 合并 A/B/C/D 四源）
  未实现。PR1 只落了域 D 自己的 `ghost-duplicates/ignored/`。域 A 的
  「`is_ignored` 只有写 True、没有改回 False」仍是既存缺口。
- **`WorkbenchDomainKey`（页面域标识）与 `ReconDomain`（导入草稿路由标签）是两个类型**，
  本次只扩前者；后者仍为 A/B/C（域 D 没有导入草稿概念，不需要扩）。
- E2E 未跑：改动不涉及路由守卫 / 布局 / permission store / 侧边栏，
  且本机无 Playwright 浏览器（下载成本高）。改动由 `pnpm typecheck` + `pnpm lint` +
  vitest（`domainQuery.spec.ts`）覆盖。
