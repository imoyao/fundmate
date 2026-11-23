/**
 * 对账中心任务元数据与队列分段（2026-11-19 场景化重构：减法 + 场景化）。
 *
 * ## 为什么从四类动作砍到三类
 * 旧页面把「待重建持仓」单独列成一张任务卡，用户要额外理解「缺字段」与
 * 「缺整条持仓行」的区别；本轮把 rebuild 折入 repair（修正数据），进入
 * rebuild 阶段抽屉时再以场景句露一次，首屏不再并列第四张卡。
 *
 * ## 分段 vs 状态
 * - `ReconQueueState`：队列项**内部**状态（后端 fixable / block_reason / status
 *   翻译而来），仍是四值；`incomplete` 只是「要你判断」的一种成因，不单独成段。
 * - `ReconQueueSegment`：用户能选的**展示分段**，只有三档（能一键处理 / 要你判断 /
 *   已处理）。`incomplete` 折叠进 judge 段（判据见 `utils/reconQueue.ts#segmentOf`）。
 *
 * ⚠️ 本文件只管展示元数据与映射，不持有数据、不推导状态。
 */
import type { WorkbenchDomainKey } from "./domainTabs";

/** 三类财务动作（rebuild 折入 repair） */
export type ReconTaskKey = "verify" | "supplement" | "repair";

/** 队列项内部待办状态：按「用户此刻能不能动手」划分，不按数据来源划分 */
export type ReconQueueState = "ready" | "judge" | "incomplete" | "done";

/** 队列展示分段：judge 段收纳 judge / incomplete 两类内部状态 */
export type ReconQueueSegment = "ready" | "judge" | "done";

export interface ReconTaskMeta {
  key: ReconTaskKey;
  /** 类型名（4 字，与侧栏叶子同一命名口径） */
  label: string;
  /** 一句话场景句：这类问题要我做什么 */
  what: string;
}

export const RECON_TASKS: readonly ReconTaskMeta[] = [
  {
    key: "verify",
    label: "核对差异",
    what: "同一笔持仓在券商流水与账本里记的份额不一致，或一笔交易被重复记账。"
  },
  {
    key: "supplement",
    label: "补记缺漏",
    what: "账上少记了一笔，按交割单把缺失的交易或扣税补上。"
  },
  {
    key: "repair",
    label: "修正数据",
    what: "记录缺字段或缺归属，补全后挂回正确的持仓或账本。"
  }
] as const;

/** 队列分段：label 用于筛选器，hint 用于队列空态引导 */
export const RECON_QUEUE_SEGMENTS: readonly {
  value: ReconQueueSegment;
  label: string;
  hint: string;
}[] = [
  {
    value: "ready",
    label: "能一键处理",
    hint: "系统已把归属算清楚，确认一次即可完成。"
  },
  {
    value: "judge",
    label: "要你判断",
    hint: "对着交割单核一下，决定按哪边记，或补上缺的那一笔。"
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
 * 域 F 只作 repair 默认落点；rebuild 已折入 repair，故此处无需再拆。
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
