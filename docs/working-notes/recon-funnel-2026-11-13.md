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
