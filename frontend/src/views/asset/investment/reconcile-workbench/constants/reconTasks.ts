/**
 * 对账中心任务卡与待办状态的展示层元数据（2026-11-07 重构；2026-11-13 漏斗重构 3 → 4 张）。
 *
 * ## 为什么不是「7 个域」
 * A~G 是后端扫描器编号，不是用户要做的事。用户打开这个页面只关心四件事：
 * 「两处数字对不上要我裁决」「账外少一笔要我补记」「记录不全要我修正」
 * 「有一段持仓要按流水重新建」，
 * 以及更关键的「我现在能处理什么」。故一级导航按**财务动作**分四张卡，
 * 队列内部按**待办状态**筛选；域编号降级为卡片上的「来源」标签。
 *
 * ⚠️ 「待重建持仓」从「修正数据」拆出来的原因：这类事缺的不是字段或归属，
 * 是整条持仓记录——补全 / 回补路径对它完全不适用（design.md「一个数据只有
 * 一个可用入口」：它有自己的阶段面板与执行区动作）。
 *
 * ⚠️ 本文件只管展示元数据与映射，不持有数据、不推导状态。
 * 可否处理的判据一律以后端 `fixable` / `block_reason` 为准（见 api/reconciliation.ts），
 * 前端照抄显示，绝不自行猜测归属。
 */

import type { WorkbenchDomainKey } from "./domainTabs";

/** 四类财务动作 */
export type ReconTaskKey = "verify" | "supplement" | "repair" | "rebuild";

/** 队列的待办状态：按「用户此刻能不能动手」划分，不按数据来源划分 */
export type ReconQueueState = "ready" | "judge" | "incomplete" | "done";

export interface ReconTaskMeta {
  key: ReconTaskKey;
  /** 卡片主标题（4 字，与侧栏叶子同一命名口径） */
  label: string;
  /** 卡片上一句话：这类问题要我做什么 */
  hint: string;
  /** 三段式说明 ① 这是什么 */
  what: string;
  /** 三段式说明 ② 放着不管会怎样（讲用户能感知的后果，不做系统自述） */
  why: string;
  /** 三段式说明 ③ 处理后会怎样（必须写清是否可撤销） */
  next: string;
  /** 收纳的原域（仅供来源标签与 ?domain= 入站寻址，不作导航维度） */
  domains: WorkbenchDomainKey[];
  /** 卡片语义色：任务性质，不表示「有多少条」。四张卡各取一个值，
   *  新增取值须同步补 `recon-task-card--<tone>` 样式（WorkbenchTaskCards.vue）。 */
  tone: "info" | "warning" | "brand" | "neutral";
}

export const RECON_TASKS: readonly ReconTaskMeta[] = [
  {
    key: "verify",
    label: "核对差异",
    hint: "两处数字对不上，需要你判断按哪边记",
    what: "同一笔持仓，券商快照和账本里记的份额不一样；也可能是一笔交易在两个账本里各记了一次。",
    why: "放着不管，账户份额会一直和券商对不上，算收益和资产时这笔会多算或少算。",
    next: "「按券商记录覆盖」会删掉账本原记录，不能撤销；「先忽略」以后还能重新对账再看。删除重复交易会重算持仓，同样不能撤销。",
    domains: ["A", "B", "D"],
    tone: "info"
  },
  {
    key: "supplement",
    label: "补记缺漏",
    hint: "账外少了一笔，按交割单补上",
    what: "账里少了一笔：券商扣的红利税还没记，或导入对账单后多出一笔没有交易流水的持仓。",
    why: "少了这笔支出，实际收益会被高估；有持仓却没流水，产品详情页也查不到它是怎么来的。",
    next: "补记后生成一笔扣税流水，能在交易流水里查看或撤销；同一标的同一天重复提交不会重复记账。系统不替你算税额——税率取决于买入批次的持股期，要对照交割单填。",
    domains: ["E", "C"],
    tone: "brand"
  },
  {
    key: "repair",
    label: "修正数据",
    hint: "记录缺字段或缺归属，报表会漏算",
    what: "有些交易没填代码、没填日期，或没有归属账本。",
    why: "它们不进任何账户视图，持仓明细、收益和资产报表都会漏掉这部分。",
    next: "系统只在能确定归属时才允许挂回，不会替你猜。补全缺失信息后能批量处理；每次回补、补全都记日志。",
    domains: ["F", "G"],
    tone: "warning"
  },
  {
    key: "rebuild",
    label: "待重建持仓",
    hint: "交易还挂在账里，但持仓记录没了，收益会漏掉这一段",
    what: "这些交易的持仓记录被删掉了，交易本身还挂着。账里也没有同标的的持仓，挂不回去。",
    why: "它们不进任何账户视图，这部分持仓的份额和收益都会漏掉。",
    next: "按流水重建会重新生成持仓行，再把交易挂回去；也可以直接删掉这些交易，删了就不能恢复。",
    domains: ["F"],
    // 与「修正数据」区分：缺的是整条持仓记录，不是字段——既非信息缺失（warning
    // 的语义），也非核对/补记，用中性色；样式待 WorkbenchTaskCards.vue 补
    // .recon-task-card--neutral（组件不在本 lane 范围）。
    tone: "neutral"
  }
] as const;

/** 待办状态：label 用于筛选器，hint 用于队列空态与卡片状态条 */
export const RECON_QUEUE_STATES: readonly {
  value: ReconQueueState;
  label: string;
  hint: string;
}[] = [
  {
    value: "ready",
    label: "可直接处理",
    hint: "系统已把范围和影响算清楚，确认一次就能完成。"
  },
  {
    value: "judge",
    label: "需要我判断",
    hint: "需要你对照凭证决定按哪边记，或补上账外那一笔。"
  },
  {
    value: "incomplete",
    label: "需先补全信息",
    hint: "缺标的代码、缺交易日期，或找不到唯一对应的账本。补全后才能继续。"
  },
  {
    value: "done",
    label: "已处理",
    hint: "本次已处理完的记录，可以凭日志编号撤销。"
  }
] as const;

/**
 * 原域 → 所属任务，**只**用于 `?domain=` 入站寻址（focusDomain 据此设任务筛选），
 * 队列归集一律读队列项自己的 `task`，不许查这张表。
 * ⚠️ 域 F 2026-11-13 起横跨 repair（补全 / 回补）与 rebuild（待重建持仓）两个任务，
 * 这里的 F → repair 只是入站默认落点（阶段面板按 activeStage 覆盖全部 F 组），
 * 不是「域 F 全部属于修正数据」的断言。
 */
export const DOMAIN_TO_TASK: Record<WorkbenchDomainKey, ReconTaskKey> = {
  A: "verify",
  B: "verify",
  C: "supplement",
  D: "verify",
  E: "supplement",
  F: "repair",
  G: "repair"
};

/** 域编号 → 用户能读懂的来源名（队列卡片上的小标签） */
export const DOMAIN_SOURCE_LABEL: Record<WorkbenchDomainKey, string> = {
  A: "E账户对账",
  B: "持仓快照",
  C: "对账单导入",
  D: "跨账本重复",
  E: "分红扣税",
  F: "数据缺失",
  G: "缺账本流水"
};

export function taskMeta(key: ReconTaskKey): ReconTaskMeta {
  const found = RECON_TASKS.find(t => t.key === key);
  if (!found) throw new Error(`未知对账任务: ${key}`);
  return found;
}

/** 队列状态优先级：可直接处理 > 需要判断 > 需先补全 > 已处理（用于默认排序） */
export const QUEUE_STATE_ORDER: Record<ReconQueueState, number> = {
  ready: 0,
  judge: 1,
  incomplete: 2,
  done: 3
};
