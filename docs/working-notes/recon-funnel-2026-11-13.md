# 对账中心域 F：阶段漏斗与唯一入口（2026-11-13）

> owner 2026-11-13 拍板：**A 阶段分流**；「删除」只放进抽屉执行区。
> 上位规范：`frontend/design.md` 的「先删，再重排」「一个数据只有一个可用入口（漏斗）」两节。

## 1. 问题（实测，非推测）

同一组 `DanglingRefGroup`（同一 `key`）在两个渲染点各出现一次，且**动作集不同**：

| 渲染点 | 何时可见 | 动作集 | 证据 |
|---|---|---|---|
| 待办队列（逐组一条） | 默认浏览路径 | 回补 / 补全 / 重建 | `utils/reconQueue.ts:423-424` 不过滤、逐组 `danglingItem(row)` |
| 域 F 面板（逐组一张卡） | 仅 `?domain=F` 直达 | 回补 / 补全 / 重建 / **删除** | `components/DomainFDanglingRefs.vue:54-64` |

后果：

- 用户看到的「下一步」取决于他从哪个入口进来（「删除」只有一条路能到）；
- 域 F 组数随账本×标的长大，队列被它挤满，其他域的待办被推到后面；
- 「只能靠重建持仓恢复」的组被挂在「修正数据」卡下，语义上它是**待重建任务**，不是差异。

## 2. 方案：阶段归属唯一（漏斗）

`danglingNextStep` 已经算出了下一步，直接把它当**阶段键**：一个组只属于一个阶段，只在一个位置渲染，只带一个主动作。

| 阶段 | 判据 | 主动作 | 分诊卡 |
|---|---|---|---|
| `fill` | 缺标的代码 | 补全信息 | 修正数据 |
| `reattach` | 后端 `fixable` | 回补关联 | 修正数据 |
| `rebuild` | 代码齐、无同标的持仓行 | 重建持仓 | **待重建持仓（新）** |
| `empty` | `txn_count === 0` | 不展示 | — |

数据流：**队列聚合项（导航）→ 阶段面板（只列组）→ 抽屉执行区（唯一动作面）**。

## 3. 结构 spec（实现口径）

### 3.1 判据层（纯函数，单一来源）

`reconcile-workbench/utils/danglingRefEnrichScope.ts` 追加：

```ts
export type DanglingStage = "fill" | "reattach" | "rebuild";
export const DANGLING_STAGES: readonly DanglingStage[];          // 固定顺序：fill → reattach → rebuild
export function danglingStageOf(input: NextStepInput): DanglingStage | null;  // empty → null
export function groupStage(group: DanglingRefGroup): DanglingStage | null;
export function bucketByStage(groups: DanglingRefGroup[]): Record<DanglingStage, DanglingRefGroup[]>;
```

硬约束：`danglingStageOf` **必须**由 `danglingNextStep` 实现（`empty → null`），禁止另写一份条件——否则阶段归属与动作名会各算一次，正是 2026-11-13 修过的漂移。

### 3.2 队列：每阶段一条聚合项

`utils/reconQueue.ts`：

- 删除逐组 `danglingItem(row)` 的产出；
- 新增 `danglingStageItem(stage, groups)`：

| 字段 | 取值 |
|---|---|
| `id` | `dangling-${stage}` |
| `task` | `fill`/`reattach` → `"repair"`；`rebuild` → `"rebuild"`（新任务） |
| `state` | `reattach` → `"ready"`；`fill`/`rebuild` → `"incomplete"` |
| `count` | 该阶段各组 `txn_count` 之和（保持和式不变量口径） |
| `actionLabel` | 阶段动作名（`DANGLING_ACTION_LABEL`） |
| `payload` | `{ kind: "danglingStage", stage, groups }` |

阶段无组 ⇒ 不产出项（空阶段不渲染）。

### 3.3 分诊卡 3 → 4

`constants/reconTasks.ts`：新增 `rebuild` 任务（`label: "待重建持仓"`）。域→任务的映射对域 F 不再够用（同一域三个任务），改成按**队列项的 `task`** 归集，而不是按 `sourceDomain` 查表。`components/WorkbenchTaskCards.vue` 排 4 卡。

**和式不变量**（`design.md:858`）：分诊卡条数 = 该任务队列项 `count` 之和。单测必须钉住。

### 3.4 抽屉：面板只导航，执行区唯一

- `composables/useWorkbenchActions.ts`：新增 `openStage(stage)`（设 `activeDomain='F'` + `activeStage=stage`，清 `activeDetailId`）；点聚合项走这条。
- `components/ReconQueueDetail.vue`：`activeStage` 非空 ⇒ 渲染阶段面板（`DomainFDanglingRefs`，只传该阶段 groups）。
- `components/DomainFDanglingRefs.vue`：**只列组，不做写操作**；组卡上抛 `openItem(group)`。
- `components/DanglingRefGroupCard.vue`：删掉 `fix` / `enrich` / `rebuild` / `remove` 四个 emit 与按钮；保留折叠明细「查看 N 条交易明细」+ 一个「处理」。
- `components/ReconItemAction.vue`（域 F 唯一动作面）：按 `payload.stage` 给

| 阶段 | 主按钮 | 次按钮 |
|---|---|---|
| `reattach` | 回补关联 | 删除 |
| `fill` | 补全信息 | 删除 |
| `rebuild` | 重建持仓 | 删除 |

「删除」复用 `DanglingRefRemediationDialog` 的 `mode="delete"`（写路径 `POST .../dangling-refs/delete/` 已有，不新增）。

### 3.5 补全弹窗收口

`DanglingRefRemediationDialog.vue` 去掉 `requestRebuild` 与「按流水重建持仓」主按钮——`rebuild` 组不再进入本弹窗，留着就是第二入口。

### 3.6 文案

删掉跨阶段指路的句子（「请到…处理」）。一个阶段内的界面只讲这一阶段的事；用户走不到别的阶段，也就不会被指错方向。

## 4. 验收

- `bucketByStage` / `danglingStageOf` / 队列聚合 / 和式不变量 / 删除只在执行区 —— 纯函数单测逐条钉住；
- 变异探针：删 `rebuild` 阶段、把聚合退回逐组、让 `danglingStageOf` 另写条件、把删除挪回组卡 —— 对应用例必须转红；
- `pnpm typecheck` 零错误；`check_vue_size --mode fail --baseline` 无回涨（`index.vue` 基线 406 行）；
- 弹窗精简后同一屏用户可见文本行数下降（design.md「先删，再重排」验收口径）。

## 5. 明确不做

- 不改后端接口、不加写路径、不动 `danglingNextStep` 的语义；
- 不动 A/B/C/D/E/G 各域的入口形态（它们各自只有一套动作面）；
- 不把「删除流水」挪去流水页（owner 已定：留在执行区）。

## 6. 追加：第 4 个阶段 `mislink`（同日，§1~§5 之后）

§1 把域 F 收成「三条修法覆盖全部脏数据」时漏了一类：流水的 `position_id` 指向一条**别的标的**的现存持仓。它不属于悬空（持仓存在）、不属于缺代码、也不能重建（同标的持仓已有），三条既有修法全都够不到，而对应 orphan 差异会永久 pending。

漏斗因此扩成四阶段，顺序 `fill → reattach → mislink → rebuild`：

| 阶段 | 判据 | 主动作 | 次动作 |
|---|---|---|---|
| `mislink` | 后端组标 `mislinked`：`position_id` 指向的持仓，其归一证券代码 ≠ 流水代码 | 改挂到正确标的 | **无**（删除端点只认悬空流水，点了必 400） |

改动落点（与 §3 并列，不覆盖）：

- 判据层：`DanglingStage` 增加 `"mislink"`；`groupStage` 首行 `if (group.mislinked) return "mislink"`（后端已判定，前端不重算）；
- 队列：`mislink` 阶段 `state = "judge"`（要人判断改成哪种），不显示批次事实，不进批量；
- 后端：新增写路径 `POST /dangling-refs/mislink/` + 预览/撤销/列表，服务 `services/dangling_ref_mislink_service.py`。两条实现口径：同账本同身份已有持仓 ⇒ 只改指针（`remount`），否则按流水重建一行（`rebuild`）；份额一律不自动重算。

**§5 第一条因此失效**：本节起域 F 有第四个写路径。它的写入仍走「预览 → `confirm is True` → `adjustment_logs` 可撤销」同一口径。

同类相邻缺陷（同 PR 内修，属对账服务自身）：`run_reconciliation` 的 `seen_keys` 过去只按 `(ledger_id, symbol)` 登记，而差异行身份是 `(ledger_id, symbol, discrepancy_type)`。补建持仓把「孤儿」变成「数量差异」后，旧 orphan 行会永久留在 pending 且再无任何入口能修——正是改挂/重建动作的必然副作用。已改为按三元组登记。

## 7. 追加：第 5 个阶段 `unowned`（2026-11-15，#3126）

§6 之后仍有第三类界外流水：`symbol` 为空**且** `position_id IS NULL`。真库 2026-11-15 实测 **254 条**，界面上**一处都看不到**——

- 不进对账（`run_reconciliation` 对缺 symbol 的行直接跳过）；
- 不进域 F（`dangling_condition` 硬要求 `position_id IS NOT NULL`）；
- 不进域 G（要求 `ledger_id IS NULL`）、不进归置（只收 `money_fund` / `reverse_repo`）。

其中 `quantity != 0` 的 **10 条**（9 笔基金卖出 + 1 笔转债兑付，`position_name` 已填、`asset_type` 为 NULL）意味着**历史卖出凭空消失**：流水页没有、持仓页份额照样算。

**判据（`dangling_identity.unowned_condition`，刻意不看 `symbol`）**：

```
family_id == fid
AND position_id IS NULL           -- 与域 F 互斥
AND covered_position_id IS NULL   -- 与归置写入互斥
AND ledger_id IS NOT NULL         -- 与域 G 互斥
AND quantity != 0                 -- 挡掉 146 条货基买卖 + 77 条分红/红利税（实测全为 0）
AND (asset_type IS NULL OR asset_type NOT IN ('money_fund','reverse_repo'))
```

**不看 `symbol`** 是全节的要害：补全标的之后 `position_id` 仍为空，谓词若看 symbol，补全动作会让这一行**再次凭空消失**。留着它，补全后有三条出路——同账本有唯一同标的持仓则夜间 `orphan_backfill_job` 自动挂回并重算份额；没有持仓行（卖出腿的常态）则在清单上继续显示「未找到相关持仓」，用户可先去建仓或删除；歧义则如实停留。

改动落点（与 §3 / §6 并列）：

- 后端：新只读端点 `GET /api/reconciliation/dangling-refs/unowned/`（载荷与 `DanglingRefList` 结构兼容），服务 `services/dangling_ref_unowned_service.py`；写路径只放开 `enrich` 与 `delete`（`_load_dangling_by_ids(..., include_unowned=True)`，默认 `False` 即安全边界），`reattach` / `rebuild` / `mislink` 对这类行继续 400——没有指针可修、没有持仓可挂。
- 判据层：`DanglingStage` 增加 `"unowned"`，顺序 `fill → unowned → reattach → mislink → rebuild`；`groupStage` **必须短路** `if (group.unowned) return "unowned"`——不短路的话，补上代码后 `danglingNextStep` 会把它派生成 `rebuild`，而 rebuild 端点对这类行必 400。这与 §6 里 `mislinked` 的短路是同一个理由：**后端已判定的身份，前端不重算**。
- 前端数据源：与错挂同一口径，在 `useWorkbenchDomains` 的 `Promise.all` 里第三次请求、`mergeDanglingLists` 合并；`fixable_count` 不涨（这类组恒不可回补，算进去等于宣称能处理一个只有两条路的阶段）。
- 队列 / 抽屉：新阶段自动被 `DANGLING_STAGES` 驱动的段渲染吸收，`ReconQueueDetail.vue` 一行未改。

**§5 第一条与 §6 的「第四个写路径」继续有效**：本节没有新增写路径，只是把既有 `enrich` / `delete` 的目标校验放宽到这一类行。

### 7.1 追加（2026-11-19）：`rebuild` 按条件放开，本篇「一律 400」已过期

上面那句「`reattach` / `rebuild` / `mislink` 三处写端点对这些行一律 400」现在只剩两个成立：
`reattach` / `mislink` 继续拒绝（没有悬空引用可挂回），**`rebuild` 放开了**。

起因是 owner 2026-11-19 的死胡同截图：字段齐全（`symbol` + `trade_date` 都有）的无归属组，
界面上只有「补全标的」，点进去弹窗里表单 / 步骤 / 预览 / 勾选全被 `needsFill === false` 隐藏，
只剩一个永远禁用的提交按钮——**一个既补不了、也重建不了、也没说为什么的弹窗**。

- **后端**：`plan_rebuild` 传 `include_unowned=True`，业务准入一条没松——净额 ≤ 0 仍拒绝
  （卖得比买多，建出来是 0 份额幽灵持仓），同账本已有同标的持仓行仍拒绝（改指向夜间回填
  `orphan_backfill_job`，**不再提「回补关联」**：那个端点对 `position_id` 为空的流水一律 400）。
  撤销把 `position_id` 还原成 `NULL`（回到无归属），不是还原成旧悬空 id。
- **前端**：阶段名仍是「属于哪一类」，动作改由 `danglingRefEnrichScope.unownedOutcome` 按组判定，
  出口四种 + 空组兜底：`fill`（还有缺字段）/ `rebuild`（字段齐·净额 > 0·无候选持仓）/
  `wait`（同账本唯一持仓，等夜间回填）/ `deleteOnly`（净额 ≤ 0 或多候选持仓）/ `empty`。
  **没有主动作时必须给原因**——`unownedOutcome` 的返回值里 `actionLabel === null` 则 `reason`
  非空，由真值表单测（`utils/__tests__/unownedOutcome.spec.ts`）钉住。
  净额门槛用 `MIN_NET_UNITS = 0.0001`（= 后端 `MIN_NET_MIN_UNITS = 1` 最小单位），
  不用 `> 0` ——`net_units` 是 float，尾数会让「前端说能建、后端说净额不足」分叉。
- **存量零产出**：真库 2026-11-19 快照里 19 条 unowned 流水 / 17 组，`types` 全为
  `sell` / `bond_redeem`、净额全为负 ⇒ 按新规则全部落在 `deleteOnly`。本次修复对存量数据的
  实际价值是**前端把话说清楚**（含「为什么重建不了」），重建放开只对未来的买入类无归属流水生效。
- 判据分工：`groupStage` 里 `if (group.unowned) return "unowned"` 的短路**继续保留**——
  它保证阶段不错派；「这一组能做哪件事」放在 `unownedOutcome`，两者不要合并。

