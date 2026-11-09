import dayjs from "dayjs";

/**
 * 资金流动区间枚举与请求参数（纯函数，不依赖 Vue / API 运行时）。
 *
 * 从 `useCashFlow.ts` 独立出来的理由：区间口径是「全周期复盘」的核心约定，
 * 必须能单测；而 composable 一导入就把 Vue 生命周期、http、格式化工具全拖进来，
 * node 环境下的单测会被这些运行时依赖绑住。这里只有 dayjs。
 *
 * `inception` 是哨兵：起点由后端按作用域解析最早一笔资金流水（含入金），
 * 前端无需先取 `first_txn_date` 再发第二次请求（冷启动鸡生蛋）。
 */
export const RANGE_OPTIONS = [
  { label: "半年", value: 180 },
  { label: "1 年", value: 365 },
  { label: "3 年", value: 1095 },
  { label: "投资以来", value: "inception" }
] as const;

export type CashFlowRange = (typeof RANGE_OPTIONS)[number]["value"];

export type CashFlowScope = {
  ledgerId?: number;
  portfolioId?: number;
};

export type CashFlowParams = {
  start_date: string;
  ledger_id?: number;
  portfolio_id?: number;
};

/**
 * 构造资金流动请求参数：终点交给后端补（今日，上海时区），这里只定起点与作用域。
 * `today` 显式注入便于单测，不在测试里依赖系统时钟。
 */
export function cashFlowParams(
  range: CashFlowRange,
  scope: CashFlowScope,
  today: ReturnType<typeof dayjs> = dayjs()
): CashFlowParams {
  const params: CashFlowParams = {
    start_date:
      range === "inception"
        ? "inception"
        : today.subtract(range, "day").format("YYYY-MM-DD")
  };
  if (scope.ledgerId != null) params.ledger_id = scope.ledgerId;
  if (scope.portfolioId != null) params.portfolio_id = scope.portfolioId;
  return params;
}
