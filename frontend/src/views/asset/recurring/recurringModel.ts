/**
 * 定投计划的展示与表单口径（#2138）。
 *
 * 纯函数集中在这里，页面只做取数与渲染：
 * - 元⇄分转换只此一处（后端一律分，用户一律元，中间不许有第三种口径）；
 * - 「每月 15 日 / 每周三 / 每两周」这类文案由 scheduleLabel 统一生成，
 *   避免表格、弹窗、汇总卡三处各写一份、日期改了漏改一处。
 */
import type {
  RecurringFrequency,
  RecurringPlan,
  RecurringStatus
} from "@/api/recurring";

export const FREQUENCY_OPTIONS: {
  value: RecurringFrequency;
  label: string;
}[] = [
  { value: "monthly", label: "每月" },
  { value: "biweekly", label: "每两周" },
  { value: "weekly", label: "每周" }
];

export const STATUS_META: Record<
  RecurringStatus,
  { label: string; type: "success" | "info" | "warning" }
> = {
  active: { label: "在投", type: "success" },
  paused: { label: "已暂停", type: "info" },
  ended: { label: "已结束", type: "info" }
};

/** 1=周一，与后端 day_of_period 语义一致 */
export const WEEKDAY_LABELS = [
  "周一",
  "周二",
  "周三",
  "周四",
  "周五",
  "周六",
  "周日"
];

export interface PlanForm {
  ledger_id: number | null;
  symbol: string;
  position_name: string;
  asset_type: string;
  /** 用户输入的是元；提交前经 yuanToCents 转分 */
  amountYuan: string;
  frequency: RecurringFrequency;
  day_of_period: number | null;
  start_date: string;
  end_date: string | null;
  note: string;
}

export const EMPTY_PLAN_FORM: PlanForm = {
  ledger_id: null,
  symbol: "",
  position_name: "",
  asset_type: "fund",
  amountYuan: "",
  frequency: "monthly",
  day_of_period: null,
  start_date: todayIso(),
  end_date: null,
  note: ""
};

/** 本地今天的 YYYY-MM-DD（不用 toISOString：那是 UTC，东八区早上 8 点前会差一天） */
export function todayIso(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** 元字符串 → 分。非法/非正数返回 null（由调用方提示，不做静默兜底 0）。 */
export function yuanToCents(input: string): number | null {
  const normalized = String(input ?? "")
    .replace(/,/g, "")
    .trim();
  if (!normalized) return null;
  const value = Number(normalized);
  if (!Number.isFinite(value) || value <= 0) return null;
  return Math.round(value * 100);
}

/** 分 → 元字符串（固定两位，供输入框回显） */
export function centsToYuan(cents: number): string {
  return ((cents || 0) / 100).toFixed(2);
}

export function planToForm(plan: RecurringPlan): PlanForm {
  return {
    ledger_id: plan.ledger_id,
    symbol: plan.symbol,
    position_name: plan.position_name ?? "",
    asset_type: plan.asset_type ?? "fund",
    amountYuan: centsToYuan(plan.amount),
    frequency: plan.frequency,
    day_of_period: plan.day_of_period,
    start_date: plan.start_date,
    end_date: plan.end_date,
    note: plan.note ?? ""
  };
}

/** 频率 + day_of_period → 「每月 15 日 / 每周三 / 每两周」 */
export function scheduleLabel(
  frequency: RecurringFrequency,
  dayOfPeriod: number | null
): string {
  if (frequency === "monthly") {
    return dayOfPeriod ? `每月 ${dayOfPeriod} 日` : "每月";
  }
  if (frequency === "weekly") {
    return dayOfPeriod ? `每周${WEEKDAY_LABELS[dayOfPeriod - 1]}` : "每周";
  }
  return "每两周";
}

/** 计划列表里的频率文案（含起止，如「每月 15 日 · 至 2027-01-15」） */
export function planScheduleLabel(plan: RecurringPlan): string {
  const base = scheduleLabel(plan.frequency, plan.day_of_period);
  return plan.end_date ? `${base} · 至 ${plan.end_date}` : base;
}

/** 表单校验：返回错误文案，null 表示通过。与后端 schemas 的约束一一对应。 */
export function validatePlanForm(form: PlanForm): string | null {
  if (!form.symbol.trim()) return "请填写标的代码";
  if (yuanToCents(form.amountYuan) === null) return "每期金额需为正数";
  if (!form.start_date) return "请选择开始日期";
  if (form.end_date && form.end_date < form.start_date) {
    return "结束日期不能早于开始日期";
  }
  const day = form.day_of_period;
  if (day !== null && day !== undefined) {
    if (form.frequency === "monthly" && (day < 1 || day > 28)) {
      return "每月扣款日需在 1~28 之间（29~31 在 2 月会跳月）";
    }
    if (form.frequency === "weekly" && (day < 1 || day > 7)) {
      return "每周扣款日需在 1~7 之间（1=周一）";
    }
    if (form.frequency === "biweekly") {
      return "每两周不需要指定星期，请清空扣款日";
    }
  }
  return null;
}

/** 汇总卡：在投计划的「每月计划投入」（分）。周投/双周投按月折算，便于横向比较。 */
export function monthlyCommittedCents(plans: RecurringPlan[]): number {
  return plans
    .filter(p => p.status === "active")
    .reduce((sum, p) => {
      if (p.frequency === "weekly") return sum + p.amount * 4;
      if (p.frequency === "biweekly") return sum + p.amount * 2;
      return sum + p.amount;
    }, 0);
}
