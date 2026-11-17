// src/views/welcome/composables/financialHealth.ts
/**
 * 首页「财务晴雨表」= 六项家庭财务健康度的取数契约与展示派生（纯函数，node 环境可测）。
 *
 * ## 六项口径（每项都写清分子 / 分母 / 数据源，禁止前端二次造数）
 *
 * 分两组，与参考设计同构但只用我们真实有的数据：
 *
 * **资产健康度**（4 项）
 * | 指标 | 比率 | 金额 | 数据源 |
 * |---|---|---|---|
 * | 资产负债率 | `liability_ratio`（后端直出 %） | `total_liabilities_cny` | summary |
 * | 投资年化收益率 | `xirr × 100`（小数转 %；无现金流守卫 null） | `total_return` | performance/xirr |
 * | 持仓集中度 | Top5 占持仓市值（后端直出） | 持仓市值 × 比率（同源反推） | position-structure |
 * | 类现金储备 | 类现金 / 家庭总资产（前端派生） | `total_net_amount` | cash-like + summary |
 *
 * **财富自由度**（2 项，2026-11 v2）
 * | 指标 | 比率 | 金额 | 数据源 |
 * |---|---|---|---|
 * | 财务自由度 | 可投资资产×3% / 预估年支出 | 可投资资产×3%（年可提取额） | assets/summary + financial-plan |
 * | 时间自由度 | 可投资资产×3% / 预估年收入 | 可投资资产×3%（年可提取额） | assets/summary + financial-plan |
 *
 * 自由度公式对齐参考设计：`可投资资产 × 3% / 年支出(年收入)`，3% 为安全提取率。
 * 可投资资产 = 家庭资产记账中「流动资金 + 投资理财」两大类合计（assets/summary 的
 * `cash`/`investment` 两项，单位元）——与参考设计给出的定义一致。
 *
 * ## 四条硬纪律
 *
 * 1. **null 不是 0**：分母缺失 / 未配置一律 null → 组件显示「—」，绝不写 0%。
 * 2. **失败不造假**：XIRR 无现金流时后端给 0.0，必须按 `cashflow_count===0` 守卫为 null。
 * 3. **不同源要标**：年化收益率与累计收益、可提取额与自由度分母口径不同，脚注写明。
 * 4. **配置是分母**：自由度分子（可提取额）与配置无关，任何时候都真实可算；
 *    只有比率需要分母，未配置时金额照显、比率显示「—」+ 引导文案。
 */
import type { PositionStructureData } from "@/api/summary";
import type { CashLikeBreakdown } from "@/api/summary";
import type { XirrData } from "@/api/performance";
import type { AssetSummaryItem } from "@/api/assets";
import type { FinancialPlanData } from "@/api/financialPlan";
import type { SummaryData } from "@/api/types";

/** 安全提取率（参考设计给定）：首年从投资资产提取的比例，之后按通胀递增。 */
export const SAFE_WITHDRAWAL_RATE = 0.03;

/** 一项健康度指标（比率 + 金额 + 口径脚注） */
export type HealthMetric = {
  key:
    | "liability"
    | "annualReturn"
    | "concentration"
    | "cash"
    | "financialFreedom"
    | "timeFreedom";
  /** 分组：资产健康度 / 财富自由度 */
  group: "asset" | "freedom";
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
  /** 比率是否由前端从同源金额派生 */
  derivedRatio: boolean;
  /** 自由度分母未配置：组件在「—」旁给「填入后显示」引导，而非干瞪眼 */
  needsConfig?: boolean;
};

/** 卡面视图：六格 + 分组 + 是否所有数据都已加载 */
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
function ratioOf(numerator: number, denominator: number | null): number | null {
  return denominator != null && denominator > 0
    ? round1((numerator / denominator) * 100)
    : null;
}

/**
 * 从真实响应派生六格。任一入参为 null 时该项 `ratio` / `amount` 为 null，
 * 由组件渲染「—」——绝不补 0。
 */
export function buildFinancialHealthView(args: {
  structure: PositionStructureData | null;
  cashLike: CashLikeBreakdown | null;
  summary: SummaryData | null;
  xirr: XirrData | null;
  assetsSummary: AssetSummaryItem[] | null;
  plan: FinancialPlanData | null;
}): FinancialHealthView {
  const totalAssets = args.summary?.total_assets_cny ?? null;

  // ① 资产负债率：比率后端直出（%）；金额 = 总负债（元）
  const liabilityRatio = args.summary?.liability_ratio ?? null;
  const liabilityAmount = args.summary?.total_liabilities_cny ?? null;

  // ② 投资年化收益率：XIRR 是小数（×100 转 %）；cashflow_count=0 时后端给 0.0 假值 → null
  const xirrHasData =
    args.xirr != null &&
    Number.isFinite(args.xirr.xirr ?? NaN) &&
    args.xirr.cashflow_count > 0;
  const annualReturnRatio = xirrHasData
    ? round1((args.xirr!.xirr as number) * 100)
    : null;
  const annualReturnAmount = xirrHasData
    ? round1(args.xirr!.total_return)
    : null;

  // ③ 集中度：比率后端直出；金额 = 持仓市值 × 比率（同源反推，分母都是持仓市值）
  const positionRatio =
    args.structure?.concentration?.top5_ratio_of_total ?? null;
  const positionValue = args.structure?.total_cny ?? null;
  const top5Amount =
    positionRatio != null && positionValue != null
      ? round1((positionValue * positionRatio) / 100)
      : null;

  // ④ 类现金：金额后端直出；比率 = 金额 / 家庭总资产（分母同源 summary）
  const cashAmount = args.cashLike?.total_net_amount ?? null;
  const cashRatio =
    cashAmount != null && totalAssets != null
      ? ratioOf(cashAmount, totalAssets)
      : null;

  // ⑤⑥ 可投资资产 = 流动资金(cash) + 投资理财(investment)，单位元。
  //     两项都拿到才算（缺一项金额会偏小，宁可给 null）。
  const cashSlice = args.assetsSummary?.find(a => a.code === "cash");
  const investmentSlice = args.assetsSummary?.find(
    a => a.code === "investment"
  );
  const investable =
    cashSlice != null && investmentSlice != null
      ? round1(cashSlice.value + investmentSlice.value)
      : null;
  // 年可提取额 = 可投资资产 × 3%（安全提取率）——与用户是否配置收支无关，恒真实
  const withdrawable =
    investable != null ? round1(investable * SAFE_WITHDRAWAL_RATE) : null;

  const expense = args.plan?.estimated_annual_expense ?? null;
  const income = args.plan?.estimated_annual_income ?? null;
  const freedomRatio =
    withdrawable != null ? ratioOf(withdrawable, expense) : null;
  const timeRatio = withdrawable != null ? ratioOf(withdrawable, income) : null;

  return {
    totalAssets,
    metrics: [
      {
        key: "liability",
        group: "asset",
        title: "资产负债率",
        ratio: liabilityRatio,
        amount: liabilityAmount,
        basis: "总负债 / 家庭总资产",
        amountNote: "负债不是亏损，涨跌色语义反转，故用品牌色中性呈现",
        derivedRatio: false
      },
      {
        key: "annualReturn",
        group: "asset",
        title: "投资年化收益率",
        ratio: annualReturnRatio,
        amount: annualReturnAmount,
        basis: "XIRR 年化（现金流转正才有值）",
        amountNote: "金额为区间累计收益，与年化率口径不同，不可相除反推",
        derivedRatio: false
      },
      {
        key: "concentration",
        group: "asset",
        title: "持仓集中度",
        ratio: positionRatio,
        amount: top5Amount,
        basis: "前五大持仓 / 持仓总市值",
        amountNote: "按后端占比反推的 Top5 市值（与前五大持仓明细同口径）",
        derivedRatio: false
      },
      {
        key: "cash",
        group: "asset",
        title: "类现金储备",
        ratio: cashRatio,
        amount: cashAmount,
        basis: "账外货基+逆回购 / 家庭总资产",
        amountNote: "已含在家庭总资产中，不重复计入任何合计",
        derivedRatio: true
      },
      {
        key: "financialFreedom",
        group: "freedom",
        title: "财务自由度",
        ratio: freedomRatio,
        amount: withdrawable,
        basis: "可投资资产×3% / 预估年支出",
        amountNote:
          expense == null
            ? "分子=年可提取额；在个人中心填入预估年支出后显示自由度"
            : "分子为年可提取额（可投资资产×3%），非实际收支",
        derivedRatio: true,
        needsConfig: expense == null
      },
      {
        key: "timeFreedom",
        group: "freedom",
        title: "时间自由度",
        ratio: timeRatio,
        amount: withdrawable,
        basis: "可投资资产×3% / 预估年收入",
        amountNote:
          income == null
            ? "分子=年可提取额；在个人中心填入预估年收入后显示自由度"
            : "分子为年可提取额（可投资资产×3%），非实际收支",
        derivedRatio: true,
        needsConfig: income == null
      }
    ]
  };
}
