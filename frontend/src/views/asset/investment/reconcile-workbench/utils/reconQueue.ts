/**
 * 对账中心「7 个后端域 → 一条用户待办队列」的映射层（2026-11-07 新增）。
 *
 * ## 为什么要这一层
 * 旧页面把 A~G 七个扫描器各开一个 tab，用户得先学会「域 F 是什么」才能找到自己要处理的
 * 记录。`domainTabs.ts` 是**后端视角**的目录，不是任务清单。本文件把七种异构数据收敛成
 * 同一种 `ReconQueueItem`：用户只看「哪笔、缺什么、现在能做什么」。
 *
 * ## 边界（务必遵守）
 * - **纯函数**：不依赖 Vue、不发请求、不改原对象；输入来自 `useWorkbenchDomains` 的快照。
 * - **不新增业务判据**：`state` 只翻译后端已给出的 `fixable` / `block_reason` / `status`，
 *   前端不自行判断「能不能修」。归属判定一律以后端为准（`api/reconciliation.ts` 注释）。
 * - **payload 原样透传**：队列项只带展示字段 + 原始对象引用，点击动作由页面层分发到
 *   既有弹窗 / composable，本层绝不触发写操作。
 * - **条数口径**：`count` 是这一项涉及的**记录条数**，不是分组数；卡片上的待办总数由
 *   `countByTask` 汇总，与「可直接处理」等状态计数同源，不各数一遍（对齐 design.md:858
 *   「和式不变量」）。
 */

import type {
  DiscrepancyItem,
  DanglingRefGroup,
  DanglingRefList,
  DividendTaxPendingItem,
  GhostDuplicateGroupItem,
  GhostDuplicateIgnore,
  OrphanLedgerGroup,
  OrphanLedgerList
} from "@/api/reconciliation";
import type { ReconciliationItem } from "@/api/eaccount";
import { centsToYuan } from "@/utils/currency";
import type { WorkbenchDomainKey } from "../constants/domainTabs";
import {
  DOMAIN_SOURCE_LABEL,
  DOMAIN_TO_TASK,
  QUEUE_STATE_ORDER,
  type ReconQueueState,
  type ReconTaskKey
} from "../constants/reconTasks";
import {
  reconAccountName,
  reconBatchLabel,
  reconCount,
  reconFlag,
  reconGroupTitle,
  reconLedgerName,
  reconMoney,
  reconMoneyPhrase,
  reconOwnership,
  reconQuantity,
  reconRecordRef,
  reconSymbolCode,
  reconTradeDate,
  reconTxnType
} from "./reconDisplay";
import {
  CASH_SYMBOL_HINT,
  discrepancyIssue,
  specialSymbolLabel
} from "./reconLabels";

/** 队列项对应的原始数据类型，供页面层分发动作（不做 any 透传） */
export type ReconQueuePayload =
  | { kind: "discrepancy"; row: DiscrepancyItem }
  | { kind: "eaccount"; row: ReconciliationItem }
  | { kind: "ghost"; row: GhostDuplicateGroupItem }
  | { kind: "ghostIgnored"; row: GhostDuplicateIgnore }
  | { kind: "tax"; row: DividendTaxPendingItem }
  | { kind: "dangling"; row: DanglingRefGroup }
  | { kind: "orphan"; row: OrphanLedgerGroup }
  | { kind: "import" };

/** 一条「用户要处理的事」。所有展示字段都已翻译成中文，不含任何内部存储码。 */
export interface ReconQueueItem {
  /** 稳定键（同一份数据重复构建必须一致，供 :key 与批量选中） */
  id: string;
  task: ReconTaskKey;
  state: ReconQueueState;
  /** 来源域只作小标签，不参与导航与排序 */
  sourceDomain: WorkbenchDomainKey;
  sourceLabel: string;
  /** 主标题：用户能认出的实体（标的代码 / 账户名 / 标的名称） */
  title: string;
  /** 一句话说清「这批是什么、缺什么」 */
  summary: string;
  /** 已翻译的辅助事实，最多 4 条；不塞内部 ID、英文枚举、ISO 时间戳 */
  facts: string[];
  /** 涉及记录条数（不是分组数） */
  count: number;
  /** 主行动按钮文案（动词 + 名词，design.md:1085） */
  actionLabel: string;
  /** 状态原因：为什么现在不能直接处理 */
  stateReason: string;
  /** 导入批次 id，供批次筛选；无批次概念的域为 null */
  batchId: number | null;
  /** 搜索串（标题 + 摘要 + 事实拼起来的小写文本） */
  searchText: string;
  payload: ReconQueuePayload;
}

export interface ReconQueueSource {
  discrepancies: DiscrepancyItem[];
  eItems: ReconciliationItem[];
  ghostGroups: GhostDuplicateGroupItem[];
  ghostIgnored: GhostDuplicateIgnore[];
  taxItems: DividendTaxPendingItem[];
  dangling: DanglingRefList | null;
  orphan: OrphanLedgerList | null;
}

function finish(
  item: Omit<ReconQueueItem, "searchText" | "sourceLabel">
): ReconQueueItem {
  const sourceLabel = DOMAIN_SOURCE_LABEL[item.sourceDomain];
  return {
    ...item,
    sourceLabel,
    searchText: [item.title, item.summary, ...item.facts, sourceLabel]
      .join(" ")
      .toLowerCase()
  };
}

/* ── 域 B / C：持仓快照差异、导入后孤儿持仓 ───────────────────────────── */

function discrepancyItem(row: DiscrepancyItem): ReconQueueItem {
  const domain = (row.domain === "C" ? "C" : "B") as WorkbenchDomainKey;
  const issue = discrepancyIssue(row.discrepancy_type);
  const done = row.status !== "pending";
  const isCash = specialSymbolLabel(row.symbol) !== null;
  return finish({
    id: `disc-${row.id}`,
    task: DOMAIN_TO_TASK[domain],
    state: done ? "done" : "judge",
    sourceDomain: domain,
    title: reconGroupTitle(row.symbol, row.display_name),
    summary: done
      ? "这条差异已经处理过了。"
      : domain === "C"
        ? "账上有这笔持仓，却找不到对应的交易流水。"
        : `${issue}，需要你对照流水决定按哪边记。`,
    facts: [
      isCash ? CASH_SYMBOL_HINT : `代码 ${reconSymbolCode(row.symbol)}`,
      row.expected_value !== null
        ? `按流水算 ${reconQuantity(row.expected_value)}`
        : "",
      row.actual_value !== null
        ? `账上记的 ${reconQuantity(row.actual_value)}`
        : "",
      row.diff !== null ? `差多少 ${reconQuantity(row.diff)}` : ""
    ].filter(Boolean),
    count: 1,
    actionLabel: done ? "查看记录" : "核对并处理",
    stateReason: done ? "已处理" : "需要你对照凭证裁决",
    batchId: null,
    payload: { kind: "discrepancy", row }
  });
}

/* ── 域 A：E账户官方快照 vs 渠道持仓 ─────────────────────────────────── */

function eaccountItem(row: ReconciliationItem): ReconQueueItem {
  const done = row.status !== "pending";
  const name = row.name?.trim();
  return finish({
    id: `eacc-${row.record_id}`,
    task: "verify",
    state: done ? "done" : "judge",
    sourceDomain: "A",
    title: name || reconGroupTitle(row.symbol),
    summary: done
      ? "这条 E账户记录已经核对过了。"
      : "E账户官方快照与账本里的份额不一致，需要你决定以哪个为准。",
    facts: [
      reconGroupTitle(row.symbol) !== "标的代码未填"
        ? `代码 ${reconGroupTitle(row.symbol)}`
        : "",
      `E账户 ${reconQuantity(row.eaccount_quantity)}`,
      `账本 ${reconQuantity(row.system_quantity)}`,
      `差额 ${reconQuantity(row.diff)}`
    ].filter(Boolean),
    count: 1,
    actionLabel: done ? "查看记录" : "核对并归因",
    stateReason: done ? "已处理" : "归因覆盖会删除渠道原记录，不可撤销",
    batchId: null,
    payload: { kind: "eaccount", row }
  });
}

/* ── 域 D：跨账本疑似重复 ───────────────────────────────────────────── */

function ghostItem(row: GhostDuplicateGroupItem): ReconQueueItem {
  const names = [...new Set(row.ledger_names.filter(Boolean))].join("、");
  const isCash = specialSymbolLabel(row.symbol) !== null;
  return finish({
    id: `ghost-${row.fingerprint}`,
    task: "verify",
    state: "judge",
    sourceDomain: "D",
    title: reconGroupTitle(row.symbol, row.display_name),
    summary: `同一笔${reconTxnType(row.txn_type)}疑似在 ${row.count} 个账本里各记了一次，需要你决定留哪一份。`,
    facts: [
      // 代码只作次要事实行：标题优先名称（reconGroupTitle 唯一口径）
      isCash ? CASH_SYMBOL_HINT : `代码 ${reconSymbolCode(row.symbol)}`,
      reconTradeDate(row.confirm_date),
      reconMoneyPhrase(row.amount_yuan),
      names ? `涉及账本 ${names}` : ""
    ].filter(Boolean),
    count: row.count,
    actionLabel: "核对重复交易",
    stateReason: "删除其中一笔会重算持仓，无法撤销",
    batchId: null,
    payload: { kind: "ghost", row }
  });
}

function ghostIgnoredItem(row: GhostDuplicateIgnore): ReconQueueItem {
  const isCash = specialSymbolLabel(row.symbol) !== null;
  return finish({
    id: `ghost-ignored-${row.id}`,
    task: "verify",
    state: "done",
    sourceDomain: "D",
    // 忽略快照可能 symbol 为 null：reconGroupTitle 统一给出可执行的降级文案
    title: reconGroupTitle(row.symbol, row.display_name),
    summary: "这组重复交易已被忽略，可以撤销后重新核对。",
    facts: [
      isCash
        ? CASH_SYMBOL_HINT
        : row.symbol
          ? `代码 ${reconSymbolCode(row.symbol)}`
          : "",
      row.confirm_date ? reconTradeDate(row.confirm_date) : "",
      row.amount_yuan !== null ? reconMoneyPhrase(row.amount_yuan) : ""
    ].filter(Boolean),
    count: 1,
    actionLabel: "撤销忽略",
    stateReason: "已忽略",
    batchId: null,
    payload: { kind: "ghostIgnored", row }
  });
}

/* ── 域 E：分红未记扣税 ─────────────────────────────────────────────── */

function taxItem(row: DividendTaxPendingItem): ReconQueueItem {
  const needRecord = row.status === "待核对";
  const isCash = specialSymbolLabel(row.symbol) !== null;
  return finish({
    id: `tax-${row.symbol}-${row.dividend_on ?? row.year}`,
    task: "supplement",
    // 税额取决于买入批次的持股期，后端不推算，一律需要用户对照交割单判断
    state: "judge",
    sourceDomain: "E",
    title: reconGroupTitle(row.symbol, row.name),
    summary: needRecord
      ? "已卖出但账里没配上这笔红利税，对照交割单确认有没有这笔扣款。"
      : "已记的扣税金额超过红利税上限，可能记错了品种，需要核对。",
    facts: [
      isCash ? CASH_SYMBOL_HINT : `代码 ${reconSymbolCode(row.symbol)}`,
      reconTradeDate(row.dividend_on),
      `税前分红 ${reconMoney(centsToYuan(row.dividend_cents))}`,
      row.tax_cents > 0
        ? `已记税 ${reconMoney(centsToYuan(row.tax_cents))}`
        : "",
      row.account_name ? `账户 ${reconAccountName(row.account_name)}` : ""
    ].filter(Boolean),
    count: 1,
    actionLabel: needRecord ? "补记这笔税" : "核对已记税额",
    stateReason: "税率取决于买入批次的持股期，需要对照交割单",
    batchId: null,
    payload: { kind: "tax", row }
  });
}

/* ── 域 F：悬空引用 / 数据缺失 ──────────────────────────────────────── */

function danglingItem(row: DanglingRefGroup): ReconQueueItem {
  // 只翻译后端判据，不自行推导：fixable 由 dangling_ref_service 一次算出
  const ready = row.fixable;
  const live = row.live_position;
  const flags = row.flags.map(reconFlag);
  const isCash = specialSymbolLabel(row.symbol) !== null;
  const summary = ready
    ? `这 ${row.txn_count} 笔交易还挂在一条已删除的持仓上。已找到现存持仓，可以挂回去。`
    : row.block_reason ||
      "这些交易缺标的代码，或找不到对应的持仓记录，暂时不能自动回补。";
  return finish({
    id: `dangling-${row.key}`,
    task: "repair",
    state: ready ? "ready" : "incomplete",
    sourceDomain: "F",
    title: reconGroupTitle(row.symbol, row.display_name),
    summary,
    facts: [
      // 代码只作次要事实行：标题优先名称（reconGroupTitle 唯一口径）
      isCash ? CASH_SYMBOL_HINT : `代码 ${reconSymbolCode(row.symbol)}`,
      reconCount(row.txn_count),
      `净额 ${reconQuantity(row.net_units)}`,
      live
        ? `现存持仓 ${reconQuantity(live.quantity)}（${reconOwnership(live.ownership_status)}）`
        : "对应持仓记录已删除",
      ...flags.slice(0, 2),
      reconBatchLabel(row.batch_label, row.txn_count)
    ],
    count: row.txn_count,
    actionLabel: ready ? "回补关联" : "补全信息",
    stateReason: ready ? "系统已找到可挂回的持仓" : "需先补全缺失信息",
    batchId: row.batch_id,
    payload: { kind: "dangling", row }
  });
}

/* ── 域 G：缺账本孤儿流水 ───────────────────────────────────────────── */

function orphanItem(row: OrphanLedgerGroup): ReconQueueItem {
  // 组级 + 逐条两级都看：后端把无法归属的原因放在 transactions[].block_reason
  const ready =
    row.block_reason === null &&
    row.transactions.length > 0 &&
    row.transactions.every(t => t.block_reason === null);
  const target = row.resolved_ledger;
  const ledgerName = reconLedgerName(target?.name);
  const summary = ready
    ? `这 ${row.txn_count} 笔流水没有账本，账户名与账本「${ledgerName}」完全一致，可以归入该账本。`
    : row.block_reason ||
      "按账户名找不到唯一对应的账本，系统不会猜测归属，需要先核对账户名。";
  return finish({
    id: `orphan-${row.key}`,
    task: "repair",
    state: ready ? "ready" : "incomplete",
    sourceDomain: "G",
    title: target?.name?.trim() || "找不到归属账本",
    summary,
    facts: [
      reconCount(row.txn_count),
      target ? `拟归入 ${ledgerName}` : "未确定目标账本",
      reconBatchLabel(row.batch_label, row.txn_count)
    ],
    count: row.txn_count,
    actionLabel: ready ? "核对并归入账本" : "查看无法归属的原因",
    stateReason: ready
      ? "归属已唯一判定，只改账本一列"
      : "账户名与账本名不一致或有歧义",
    batchId: row.batch_id,
    payload: { kind: "orphan", row }
  });
}

/* ── 域 C 入口：导入不是待办，但要有明确的行动卡 ────────────────────── */

function importItem(): ReconQueueItem {
  return finish({
    id: "import-entry",
    task: "supplement",
    state: "judge",
    sourceDomain: "C",
    title: "导入交割单",
    summary:
      "从券商或表格文件批量导入交易，系统会自动找出有持仓却没有交易流水的记录。",
    facts: ["导入后自动找出缺流水的持仓", "份额差异在「核对差异」里看"],
    count: 0,
    actionLabel: "查看导入入口",
    stateReason: "这是入口动作，不是待处理记录",
    batchId: null,
    payload: { kind: "import" }
  });
}

/**
 * 数组守卫：后端一旦返回 HTTP 200 但 body 形状不对（例如把汇总对象当清单返回），
 * `for...of` 会在 computed 里抛错。Vue 对渲染错误很「包容」——不白屏、不崩，
 * 只把 DOM 冻在末次成功渲染（加载态），用户看到的是「一直转圈」而不是报错。
 * 这里统一降级成空数组，让错误态由 loader 的 loadErrors 正常表达。
 */
function rowsOf<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

/** 把七域快照收敛成一条待办队列。顺序由调用方排序，本函数不排序。 */
export function buildReconQueue(source: ReconQueueSource): ReconQueueItem[] {
  const items: ReconQueueItem[] = [];

  for (const row of rowsOf(source.discrepancies)) {
    if (row.domain === "B" || row.domain === "C")
      items.push(discrepancyItem(row));
  }
  for (const row of rowsOf(source.eItems)) items.push(eaccountItem(row));
  for (const row of rowsOf(source.ghostGroups)) items.push(ghostItem(row));
  for (const row of rowsOf(source.ghostIgnored))
    items.push(ghostIgnoredItem(row));
  for (const row of rowsOf(source.taxItems)) items.push(taxItem(row));
  for (const row of rowsOf(source.dangling?.groups))
    items.push(danglingItem(row));
  for (const row of rowsOf(source.orphan?.groups)) items.push(orphanItem(row));

  items.push(importItem());
  return items;
}

/** 队列默认排序：可直接处理 → 需要判断 → 需先补全 → 已处理；同档按涉及条数降序 */
export function sortQueue(items: ReconQueueItem[]): ReconQueueItem[] {
  return [...items].sort((a, b) => {
    const byState = QUEUE_STATE_ORDER[a.state] - QUEUE_STATE_ORDER[b.state];
    if (byState !== 0) return byState;
    return b.count - a.count;
  });
}

export interface ReconQueueFilter {
  task: ReconTaskKey | "all";
  state: ReconQueueState | "all";
  keyword: string;
  batchId: number | "all";
}

export const DEFAULT_QUEUE_FILTER: ReconQueueFilter = {
  task: "all",
  state: "all",
  keyword: "",
  batchId: "all"
};

/** 筛选：四个维度同时生效，全部走纯函数，页面只传值 */
export function filterQueue(
  items: ReconQueueItem[],
  filter: ReconQueueFilter
): ReconQueueItem[] {
  const keyword = filter.keyword.trim().toLowerCase();
  return items.filter(item => {
    if (filter.task !== "all" && item.task !== filter.task) return false;
    if (filter.state !== "all" && item.state !== filter.state) return false;
    if (filter.batchId !== "all" && item.batchId !== filter.batchId)
      return false;
    if (keyword && !item.searchText.includes(keyword)) return false;
    return true;
  });
}

/**
 * 分诊卡计数：卡上条数 = 该任务下待办记录条数之和，与状态筛选后的列表同源。
 * 「已处理」不计入待办数，但状态筛选里仍可查看。
 */
export function countByTask(
  items: ReconQueueItem[],
  task: ReconTaskKey
): number {
  return items
    .filter(i => i.task === task && i.state !== "done")
    .reduce((sum, i) => sum + i.count, 0);
}

/**
 * 分诊卡角标：这一任务下还有几**件**待办。
 * 与 `countByTask` 的区别是口径：`countByTask` 数「涉及多少条记录」（如 663 条流水），
 * 角标数「要打开处理几次」（如 122 组）。用户点卡片时关心的是后者；
 * 记录条数放在任务说明里。入口动作（count=0）与已处理项都不算待办。
 */
export function countOpenItemsByTask(
  items: ReconQueueItem[],
  task: ReconTaskKey
): number {
  return items.filter(i => i.task === task && i.state !== "done" && i.count > 0)
    .length;
}

/** 状态分段器的计数：与筛选后列表同源，不另数一遍 */
export function countByState(
  items: ReconQueueItem[],
  task: ReconTaskKey | "all"
): Record<ReconQueueState, number> {
  const counts: Record<ReconQueueState, number> = {
    ready: 0,
    judge: 0,
    incomplete: 0,
    done: 0
  };
  for (const item of items) {
    if (task !== "all" && item.task !== task) continue;
    counts[item.state] += 1;
  }
  return counts;
}

/** 批次下拉选项（去重 + 稳定排序），只列真实存在的批次 */
export function queueBatchOptions(items: ReconQueueItem[]): Array<{
  id: number;
  label: string;
}> {
  const seen = new Map<number, string>();
  for (const item of items) {
    if (item.batchId === null || seen.has(item.batchId)) continue;
    const batchFact = item.facts.find(f => f.startsWith("来自 "));
    seen.set(item.batchId, batchFact ?? `批次 ${item.batchId}`);
  }
  return [...seen.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([id, label]) => ({ id, label }));
}

/** 可供批量处理的项：只有「可直接处理」且后端判定可修的才能进批量 */
export function batchableItems(items: ReconQueueItem[]): ReconQueueItem[] {
  return items.filter(
    i =>
      i.state === "ready" &&
      (i.payload.kind === "dangling" || i.payload.kind === "orphan")
  );
}

/** 明细行的用户语言（供卡片展开区复用，不再手写 `#57 buy ...`） */
export function danglingDetailLine(t: {
  id: number;
  txn_type: string;
  trade_date: string | null;
  quantity: number;
  amount: number;
  position_id: number;
}): {
  date: string;
  type: string;
  quantity: string;
  amount: string;
  note: string;
} {
  return {
    date: reconTradeDate(t.trade_date),
    type: reconTxnType(t.txn_type),
    quantity: reconQuantity(t.quantity),
    amount: reconMoneyPhrase(t.amount),
    note: `指向已删除的持仓（${reconRecordRef(t.position_id)}）`
  };
}

/** 缺账本流水明细行的用户语言 */
export function orphanDetailLine(t: {
  id: number;
  txn_type: string;
  trade_date: string | null;
  account_name: string | null;
  amount: number;
  block_reason: string | null;
  resolved_ledger_id: number | null;
}): {
  date: string;
  type: string;
  account: string;
  amount: string;
  result: string;
  blocked: boolean;
} {
  return {
    date: reconTradeDate(t.trade_date),
    type: reconTxnType(t.txn_type),
    account: reconAccountName(t.account_name),
    amount: reconMoneyPhrase(t.amount),
    result: t.block_reason ?? "可归入对应账本",
    blocked: t.block_reason !== null
  };
}
