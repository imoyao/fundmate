// src/views/welcome/composables/financialHealth.ts
/**
 * 首页「财务晴雨表」= 四项资产健康度的取数契约与展示派生（纯函数，node 环境可测）。
 *
 * ## 为什么要有这个模块
 *
 * 2026-11-10 之前这张卡是「即将上线」空态，info 文案还挂着「预估储蓄率 / 财务自由度」——
 * 那两项要家庭月度收支，全仓零数据（见 `docs/spec/cashflow-layers.md` 与 `docs/todo.md`），
 * 做不出来。用户拍板重定义为**资产健康度**：只用现有真实指标，每项同时给「比率 + 金额」。
 *
 * ## 四项口径（每项都写清分子 / 分母 / 数据源，禁止前端二次造数）
 *
 * | 指标 | 比率 | 金额 | 数据源 |
 * |---|---|---|---|
 * | 持仓集中度 | Top5 占持仓市值（**后端直出** `top5_ratio_of_total`） | 持仓市值 × 比率（同源反推，卡面标「推算」） | position-structure |
 * | 类现金储备 | 类现金 / 家庭总资产（**前端派生**，分母同源 summary） | `total_net_amount`（账外货基/逆回购，已含在总资产） | cash-like + summary |
 * | 近 12 月净分红 | 在管持仓股息率 `yield_on_value_pct`（**后端直出**） | `totals.ttm.net_cents` 转元（全流水含已清仓） | dividends/summary |
 * | 组合目标达成 | `target_progress`（市值/目标，仅已设目标组合） | 已设目标组合的市值合计 | portfolios |
 *
 * ## 三条硬纪律
 *
 * 1. **不同源要标**：分红金额（全流水）与股息率（在管持仓）分母不同，卡面脚注必须写明；
 *    禁止把两个口径的数并列相加，也禁止拿金额反算比率冒充同源。
 * 2. **null 不是 0**：`target_progress` 为 null（未设目标）不参与均值、不显示 0%；
 *    分母为 0 时比率返回 null，由组件显示「—」。
 * 3. **失败不造假**：任一接口失败由 composable 置 error，本模块不接收假数、不回落占位。
 */

import type { PositionStructureData } from "@/api/summary";
import type { CashLikeBreakdown } from "@/api/summary";
import type { DividendSummary } from "@/api/dividends";
import type { PortfolioItem } from "@/api/portfolio";
import type { SummaryData } from "@/api/types";

/** 一项健康度指标（比率 + 金额 + 口径脚注） */
export type HealthMetric = {
  key: "concentration" | "cash" | "dividend" | "goal";
  /** 卡面标题（前端固定文案，不是后端枚举） */
  title: string;
  /** 比率（%）；null = 分母缺失 / 无数据，组件显示「—」而非 0% */
  ratio: number | null;
  /** 金额（元）；null = 不可得 */
  amount: number | null;
  /** 比率的分母说明，告诉用户「这个百分比是相对什么算的」 */
  basis: string;
  /** 金额来源说明（含不同源提示 / 防双计提示） */
  amountNote: string;
  /** 比率是否由前端从同源金额派生（集中度是后端直出，类现金是前端派生） */
  derivedRatio: boolean;
};

/** 卡面视图：四格 + 是否所有数据都已加载 */
export type FinancialHealthView = {
  metrics: HealthMetric[];
  /** 家庭总资产（元），类现金占比的分母；null = summary 未加载 */
  totalAssets: number | null;
};

const round1 = (n: number): number => Math.round(n * 10) / 10;

/**
 * 安全除法：分母非正返回 null（「算不了」不是 0%）。
 * 与后端 `summary_service.ratio_pct` 的 null 语义一致。
 */
function ratioOf(numerator: number, denominator: number): number | null {
  return denominator > 0 ? round1((numerator / denominator) * 100) : null;
}

/**
 * 从五个真实响应派生四格。任一入参为 null 时该项 `ratio` / `amount` 为 null，
 * 由组件渲染「—」——绝不补 0。
 */
export function buildFinancialHealthView(args: {
  structure: PositionStructureData | null;
  cashLike: CashLikeBreakdown | null;
  dividend: DividendSummary | null;
  portfolios: PortfolioItem[] | null;
  summary: SummaryData | null;
}): FinancialHealthView {
  const totalAssets = args.summary?.total_assets_cny ?? null;

  // ① 集中度：比率后端直出；金额 = 持仓市值 × 比率（同源反推，分母都是持仓市值）
  const positionRatio =
    args.structure?.concentration?.top5_ratio_of_total ?? null;
  const positionValue = args.structure?.total_cny ?? null;
  const top5Amount =
    positionRatio != null && positionValue != null
      ? round1((positionValue * positionRatio) / 100)
      : null;

  // ② 类现金：金额后端直出；比率 = 金额 / 家庭总资产（分母同源 summary）
  const cashAmount = args.cashLike?.total_net_amount ?? null;
  const cashRatio =
    cashAmount != null && totalAssets != null
      ? ratioOf(cashAmount, totalAssets)
      : null;

  // ③ 分红：金额 = TTM 净分红（分→元，全流水）；比率 = 在管持仓股息率（后端直出）
  //   两者不同源：金额含已清仓标的，股息率只算在管持仓——脚注写明。
  const dividendAmount = args.dividend
    ? args.dividend.totals.ttm.net_cents / 100
    : null;
  const dividendRatio = args.dividend?.portfolio?.yield_on_value_pct ?? null;

  // ④ 组合目标达成：比率 = 已设目标组合的 target_progress 均值；
  //   金额 = 这些组合的市值合计。未设目标的组合既不进分子也不进分母。
  const withTarget = (args.portfolios ?? []).filter(
    p =>
      p.target_progress != null &&
      Number.isFinite(p.target_progress) &&
      (p.market_value ?? 0) > 0
  );
  const goalRatio =
    withTarget.length > 0
      ? round1(
          withTarget.reduce((s, p) => s + (p.target_progress as number), 0) /
            withTarget.length
        )
      : null;
  const goalAmount =
    withTarget.length > 0
      ? round1(withTarget.reduce((s, p) => s + (p.market_value as number), 0))
      : null;

  return {
    totalAssets,
    metrics: [
      {
        key: "concentration",
        title: "持仓集中度",
        ratio: positionRatio,
        amount: top5Amount,
        basis: "前五大持仓 / 持仓总市值",
        amountNote: "按后端占比反推的 Top5 市值（与前五大持仓明细同口径）",
        derivedRatio: false
      },
      {
        key: "cash",
        title: "类现金储备",
        ratio: cashRatio,
        amount: cashAmount,
        basis: "账外货基+逆回购 / 家庭总资产",
        amountNote: "已含在家庭总资产中，不重复计入任何合计",
        derivedRatio: true
      },
      {
        key: "dividend",
        title: "近 12 月净分红",
        ratio: dividendRatio,
        amount: dividendAmount,
        basis: "在管持仓股息率（净分红/持仓市值）",
        amountNote: "金额为全流水净额（含已清仓），与股息率口径不同",
        derivedRatio: false
      },
      {
        key: "goal",
        title: "组合目标达成",
        ratio: goalRatio,
        amount: goalAmount,
        basis: `已设目标组合的达成率均值（${withTarget.length} 个）`,
        amountNote: "仅统计已设目标金额的组合；未设目标的不计入",
        derivedRatio: false
      }
    ]
  };
}
