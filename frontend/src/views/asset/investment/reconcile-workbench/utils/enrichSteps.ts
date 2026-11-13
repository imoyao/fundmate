/**
 * 「补全信息」三步准入的**展示态翻译**（对账工作台域 F）。
 *
 * 判据的唯一真相源仍是 `danglingRefRemediationGuard`：本文件只把 guard 返回的
 * 阻塞原因翻译成「现在在第几步 / 下一步做什么」，不新增任何准入条件、也不改文案
 * 契约。目的：打开弹窗时看到的是流程，而不是一句「请至少填写……」的报错。
 */
import {
  enrichBlockReason,
  type EnrichBlockReason,
  type EnrichGuardInput
} from "./danglingRefRemediationGuard";

export const ENRICH_STEPS = [
  { title: "填缺失信息", hint: "标的代码或交易日期，至少填一项" },
  { title: "查看影响", hint: "确认会改动哪些交易" },
  { title: "核对并确认", hint: "勾选确认后即可提交" }
] as const;

type Reason = Exclude<EnrichBlockReason, null>;
type StepIndex = 1 | 2 | 3;

const STEP_BY_REASON: Record<Reason, StepIndex> = {
  该组没有可处理的交易: 1,
  这组没有可补的字段: 1,
  请至少填写标的代码或交易日期: 1,
  正在查看影响: 2,
  请先查看影响: 2,
  "输入已变化，请重新查看影响": 2,
  正在提交: 3,
  请先勾选二次确认: 3
};

/** 引导语一律写「下一步做什么」，不写命令式报错；错误文案留在 guard 里。 */
const GUIDE_BY_REASON: Record<Reason, string> = {
  该组没有可处理的交易: "这一组没有可处理的交易，请回到列表核对。",
  这组没有可补的字段:
    "这组流水的标的代码与交易日期都已填写，没有可补的字段；要继续处理，需补建持仓或补录流水。",
  请至少填写标的代码或交易日期: "下一步：填写标的代码或交易日期（至少一项）。",
  正在查看影响: "正在核对这次改动的影响…",
  请先查看影响: "下一步：点「查看影响」，确认会改动哪些交易。",
  "输入已变化，请重新查看影响": "输入变了，请重新查看影响后再提交。",
  正在提交: "正在写入…",
  请先勾选二次确认: "最后一步：核对影响后勾选「我已核对」。"
};

export interface EnrichStepState {
  /** 当前停在第几步；null = 三步全部完成 */
  current: StepIndex | null;
  /** 已完成的步数，用于清单打勾 */
  completed: number;
  guide: string;
  blocked: boolean;
}

export function describeEnrichSteps(input: EnrichGuardInput): EnrichStepState {
  const reason = enrichBlockReason(input);
  if (!reason) {
    return {
      current: null,
      completed: ENRICH_STEPS.length,
      guide: "三步已完成，可以确认补全。",
      blocked: false
    };
  }
  const current = STEP_BY_REASON[reason];
  return {
    current,
    completed: current - 1,
    guide: GUIDE_BY_REASON[reason],
    blocked: true
  };
}
