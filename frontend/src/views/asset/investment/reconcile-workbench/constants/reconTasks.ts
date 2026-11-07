/**
 * 对账中心任务卡与待办状态的展示层元数据（2026-11-07 重构）。
 *
 * ## 为什么不是「7 个域」
 * A~G 是后端扫描器编号，不是用户要做的事。用户打开这个页面只关心三件事：
 * 「两处数字对不上要我裁决」「账外少一笔要我补记」「记录不全要我修正」，
 * 以及更关键的「我现在能处理什么」。故一级导航按**财务动作**分三张卡，
 * 队列内部按**待办状态**筛选；域编号降级为卡片上的「来源」标签。
 *
 * ⚠️ 本文件只管展示元数据与映射，不持有数据、不推导状态。
 * 可否处理的判据一律以后端 `fixable` / `block_reason` 为准（见 api/reconciliation.ts），
 * 前端照抄显示，绝不自行猜测归属。
 */

import type { WorkbenchDomainKey } from "./domainTabs";

/** 三类财务动作 */
export type ReconTaskKey = "verify" | "supplement" | "repair";

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
  /** 三段式说明 ② 为什么找我 / 影响什么 */
  why: string;
  /** 三段式说明 ③ 处理后会怎样（必须写清是否可撤销） */
  next: string;
  /** 收纳的原域（仅供来源标签与 ?domain= 入站寻址，不作导航维度） */
  domains: WorkbenchDomainKey[];
  /** 卡片语义色：任务性质，不表示「有多少条」 */
  tone: "info" | "warning" | "brand";
}

export const RECON_TASKS: readonly ReconTaskMeta[] = [
  {
    key: "verify",
    label: "核对差异",
    hint: "两处数字对不上，需要你判断按哪边记",
    what: "同一笔持仓在两个地方的记录对不上，或有交易疑似被重复记了两次。",
    why: "资产报表只能取其中一个数，不裁决就可能一直算错。",
    next: "「归因覆盖」会以 E账户快照为准并删除渠道原记录，不可撤销；「忽略」可稍后重新对账恢复。删除重复交易会重算持仓，也无法撤销。",
    domains: ["A", "B", "D"],
    tone: "info"
  },
  {
    key: "supplement",
    label: "补记缺漏",
    hint: "账外少了一笔，按交割单补上",
    what: "有现金分红，券商在交割单上扣了红利税，账里还没有这笔扣税流水。",
    why: "少了这笔支出，实际收益会被高估。",
    next: "补记后生成一笔扣税流水，可在交易流水中查看或撤销；同一标的同一天重复提交不会重复记账。系统不替你推算税额——税率取决于买入批次的持股期。",
    domains: ["E", "C"],
    tone: "brand"
  },
  {
    key: "repair",
    label: "修正数据",
    hint: "记录缺字段或缺归属，报表会漏算",
    what: "这些交易找不到对应的持仓记录，或缺少标的代码、交易日期，也没有归属账本。",
    why: "它们不进任何账户视图，持仓明细、收益与资产报表都会漏算这部分。",
    next: "系统只在能确定归属时才允许回补，不会替你猜。先补全缺失信息，再批量挂回；每次回补、补全、删除都可凭日志编号撤销。",
    domains: ["F", "G"],
    tone: "warning"
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

/** 原域 → 所属任务。`?domain=F` 入站时据此定位到任务卡，不改变域本身的含义 */
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
