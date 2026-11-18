/**
 * 账户详情「账本概览」指标格的数据源（2026-11-15 从 LedgerDetailOverview 抽出）。
 *
 * 为什么单拎出来：那页原本 8 个指标格是 8 段复制粘贴，其中 3~4 格常年是 `--`，
 * 空占两行高度。改成数组驱动后逻辑变长了，正好顶破页面规模门禁（400 行），
 * 故按 #980 的做法把「算什么」放到这里，页面只留「画什么」。
 *
 * 核心判据只有一条：**没有值的指标不生成格子**。`--` 不是信息，一屏三个 `--`
 * 反而把真正有数的持仓盈亏压下去；缺数据时页面少一格，比多一格灰噪点诚实。
 */

/** 一格指标。`value` 为 null 的条目由调用方过滤掉（不渲染空格）。 */
export type MetricCell =
  | {
      key: string;
      label: string;
      kind: "money";
      value: number;
      /** 按涨跌着色（持仓/收益类 true，余额类 false） */
      signed?: boolean;
      /** 固定危险色（如关联负债） */
      danger?: boolean;
      hint?: string;
    }
  | { key: string; label: string; kind: "rate"; value: number; hint?: string }
  | { key: string; label: string; kind: "count"; value: number; hint?: string };

export type OverviewMetricInput = {
  /** 账户 summary（后端字段缺失一律视为「没有这个口径」） */
  summary: {
    position_count?: number | null;
    cash_balance?: number | null;
    ledger_type?: string | null;
    linked_liability?: number | null;
  } | null;
  /** 货基当日收益（仅基金账户可能拿到） */
  moneyFundIncome?: number | null;
  /** 近 90 天区间收益 / 基准同期 / 超额（后端缺数据为 null） */
  rangeRate?: number | null;
  benchmarkReturn?: number | null;
  excessReturn?: number | null;
  /** 超额收益的降级原因（有则作为悬浮提示） */
  excessHint?: string | null;
};

/** 组装概览指标格（顺序即版面顺序：持仓数量 → 资金 → 负债 → 货基 → 区间对比）。 */
export function buildOverviewMetrics(input: OverviewMetricInput): MetricCell[] {
  const s = input.summary;
  const cells: Array<MetricCell | null> = [
    {
      key: "position-count",
      label: "持仓数量",
      kind: "count",
      value: s?.position_count ?? 0
    },
    // 资金余额：后端不下发就是「这个账户没有现金口径」，不画 `--`；
    // 为 0 也不画——「余额 ¥0.00」只说明满仓，而这句话类现金区块已经说了，
    // 且它会独占一行的最后一格（2026-11-15 实测 5 格 / 4 列 → 第二行挂一个空格）。
    s?.cash_balance != null && s.cash_balance !== 0
      ? {
          key: "cash-balance",
          label: "资金余额",
          kind: "money",
          value: s.cash_balance
        }
      : null,
    // 关联负债：只对银行账户、且真的有负债时才是一件事
    s?.ledger_type === "bank" && (s?.linked_liability ?? 0) > 0
      ? {
          key: "linked-liability",
          label: "关联负债",
          kind: "money",
          value: -(s.linked_liability as number),
          danger: true,
          hint: "本账户关联的贷款 / 负债余额（负数表示欠款）"
        }
      : null,
    // 货基今日收益：仅基金账户、且拿到货基口径时出现（与「当日收益」并列不相加）
    s?.ledger_type === "fund" && input.moneyFundIncome != null
      ? {
          key: "money-fund-income",
          label: "货基今日收益",
          kind: "money",
          value: input.moneyFundIncome,
          hint: "货币基金当日收益，与「当日收益」是两套口径，不相加"
        }
      : null,
    input.rangeRate != null
      ? {
          key: "range-rate",
          label: "近 90 天收益",
          kind: "rate",
          value: input.rangeRate
        }
      : null,
    input.benchmarkReturn != null
      ? {
          key: "benchmark-return",
          label: "基准同期",
          kind: "rate",
          value: input.benchmarkReturn,
          hint: "同区间、同口径的业绩基准收益"
        }
      : null,
    input.excessReturn != null
      ? {
          key: "excess-return",
          label: "超额收益",
          kind: "rate",
          value: input.excessReturn,
          hint: input.excessHint || "区间收益 − 基准同期收益"
        }
      : null
  ];
  return cells.filter((cell): cell is MetricCell => cell !== null);
}
