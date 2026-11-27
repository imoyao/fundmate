import dayjs from "dayjs";
import { chartRangeParams, type ChartRangeKey } from "@/utils/chartRange";

/**
 * 资金流动的请求参数（纯函数，不依赖 Vue / API 运行时）。
 *
 * 从 `useCashFlow.ts` 独立出来的理由：区间口径是「全周期复盘」的核心约定，
 * 必须能单测；而 composable 一导入就把 Vue 生命周期、http、格式化工具全拖进来，
 * node 环境下的单测会被这些运行时依赖绑住。
 *
 * ## 区间枚举已归一到 `utils/chartRange.ts`（#3107）
 *
 * 这里曾经自带一份 `180 / 365 / 1095 / inception` 的枚举，与同页「超额走势」
 * （写死 90 天）、「收益归因」（1m/3m/ytd/1y/all）三套并存——同一个「近1年」
 * 在三处能落在不同起点。现在三处共用一份档位表，本文件只负责把它翻成请求参数。
 *
 * `inception` 仍是哨兵：起点由后端按作用域解析最早一笔资金流水（含入金），
 * 前端无需先取 `first_txn_date` 再发第二次请求（冷启动鸡生蛋）。
 */
export type CashFlowRange = ChartRangeKey;

export type CashFlowScope = {
  ledgerId?: number;
  portfolioId?: number;
  /**
   * 家庭级（2026-11-27）：没有 id 可推断，须显式标识。
   * 后端把「两个 id 都不传」当参数错误而不是「默认全家」——漏传就退回全家数据
   * 是比报错更坏的结果，故这里也必须显式。
   */
  family?: boolean;
};

export type CashFlowParams = {
  start_date: string;
  scope?: "family";
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
    start_date: chartRangeParams(range, today).start_date
  };
  if (scope.family) {
    // 家庭级与 id 互斥（后端同传 400）：只要标了 family 就不带 id
    params.scope = "family";
    return params;
  }
  if (scope.ledgerId != null) params.ledger_id = scope.ledgerId;
  if (scope.portfolioId != null) params.portfolio_id = scope.portfolioId;
  return params;
}
