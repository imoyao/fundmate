/**
 * 组合内基金两两相关性矩阵（#2686 第二交付）。
 *
 * 与重叠度矩阵的关系：**同一份成员、同一条截断规则**（后端 `matrix_members.py`），
 * 只是格子里的数换成 ρ。两张矩阵能对照，前提是行列一致——所以这个文件**不截断成员**，
 * 只负责铺格与文案。
 *
 * 五种格子（**不可合并**）：
 * - `self` 自比（对角线）：「—」，不是 1.00；
 * - `high` / `mid` / `low` / `negative` 按 ρ 分档（正相关高 = 一起涨一起跌 = 分散无效）；
 * - `unavailable` 算不出来：**必须写清是哪种算不出**——无净值 / 样本不足 / 净值无波动。
 *   画成 0 就是在说「不相关」，而真相是「没有信息」。
 *
 * 阈值只在这里定义一次：ρ 分档是展示口径（不是统计结论），放后端反而要为一个
 * 换色需求改服务端。
 */

import type {
  CorrelationCell,
  CorrelationFund,
  CorrelationStatus,
  HoldingCorrelationData
} from "@/api/holdingOverlap";

export type CorrelationTone =
  "self" | "high" | "mid" | "low" | "negative" | "unavailable";

export interface CorrelationCellView {
  /** 格子里的文字：`0.46` / `—` / `样本不足` / `无净值` / `无波动` */
  text: string;
  tone: CorrelationTone;
  /** 悬停说明：这个格子为什么是这个值（尤其「算不出」必须给原因与样本数） */
  title: string;
}

export interface CorrelationRow {
  fund: CorrelationFund;
  cells: CorrelationCellView[];
}

export interface CorrelationMatrix {
  funds: CorrelationFund[];
  rows: CorrelationRow[];
  /** 可算出对数 / 总对数（`totalPairs=0` 时比例无意义，展示层显示「—」） */
  computedPairs: number;
  totalPairs: number;
  truncatedCount: number;
  truncatedMarketValuePct: number;
  /** 已展开部分覆盖的市值比例（%）= 100 - truncatedMarketValuePct */
  coveragePct: number;
  /** 覆盖说明（含未覆盖只数与占比）——必须与矩阵同屏 */
  coverageText: string;
  window: string;
  minOverlap: number;
}

/** 三种「算不出」的展示文案：含义不同，文案就不能相同 */
const STATUS_TEXT: Record<CorrelationStatus, string> = {
  ok: "",
  no_series: "无净值",
  short_overlap: "样本不足",
  zero_variance: "无波动"
};

/** 三种「算不出」的完整说明（悬停用） */
const STATUS_HINT: Record<CorrelationStatus, string> = {
  ok: "",
  no_series: "该基金没有净值/价格序列（新成立或未入库），不是「不相关」",
  short_overlap: "同期交易日不足，样本太少算不出稳定相关系数，不是「不相关」",
  zero_variance:
    "净值长期不变（货基/停牌），相关系数在数学上未定义，不是「不相关」"
};

/**
 * ρ → 视觉档位。
 *
 * 语义：正相关高 = 一起涨一起跌 = 「以为分散、其实没有」，用警示色；负相关是天然对冲，
 * 用相反的色。阈值 0.8 / 0.5 / -0.3 取整是为了让 96 对里能分出层次（实测中位 0.46）。
 */
export function correlationTone(
  rho: number | null | undefined
): CorrelationTone {
  if (rho === null || rho === undefined || Number.isNaN(rho)) {
    return "unavailable";
  }
  if (rho >= 0.8) return "high";
  if (rho >= 0.5) return "mid";
  if (rho >= -0.3) return "low";
  return "negative";
}

/** ρ 文字：两位小数、负号保留（`-0.32`），不写成百分比 */
export function formatRho(rho: number | null | undefined): string {
  if (rho === null || rho === undefined || Number.isNaN(rho)) return "—";
  return rho.toFixed(2);
}

/** 无序基金对键：矩阵对称，a/b 顺序不代表方向 */
function pairKeyOf(codeA: string, codeB: string): string {
  return [codeA, codeB].sort().join("|");
}

function buildCell(
  rowFund: CorrelationFund,
  colFund: CorrelationFund,
  cell: CorrelationCell | undefined
): CorrelationCellView {
  if (rowFund.fund_code === colFund.fund_code) {
    return { text: "—", tone: "self", title: "同一只基金，不参与比较" };
  }
  if (!cell) {
    // 取数缺口 ≠ 算不出：这两件事的处置方式不同（缺口要查后端），文案也不许复用
    return {
      text: "—",
      tone: "unavailable",
      title: "后端未返回这一对的结果（取数缺口，不是「不相关」）"
    };
  }
  if (cell.status !== "ok") {
    return {
      text: STATUS_TEXT[cell.status] ?? "算不出",
      tone: "unavailable",
      title: `${STATUS_HINT[cell.status] ?? ""}（${cell.reason || "原因未给出"}；同期 ${cell.overlap_days} 天）`
    };
  }
  return {
    text: formatRho(cell.correlation),
    tone: correlationTone(cell.correlation),
    title: `相关系数 ${formatRho(cell.correlation)}（同期 ${cell.overlap_days} 个交易日）`
  };
}

/** 覆盖说明：把「未展开多少、占多少市值」说清楚，不许只留一个矩阵就跑 */
function coverageTextOf(
  data: HoldingCorrelationData,
  funds: CorrelationFund[]
): string {
  if (data.fund_count < 2) return "可比基金不足 2 只，无法两两比较";
  if (!data.truncated.count) {
    return `已展开全部 ${funds.length} 只基金，覆盖全部基金持仓市值`;
  }
  const covered = (100 - data.truncated.market_value_pct).toFixed(1);
  return (
    `已展开前 ${funds.length} 只（覆盖 ${covered}% 基金市值）；` +
    `另有 ${data.truncated.count} 只（${data.truncated.market_value_pct}%）未展开，` +
    `本次结论仅代表已展开部分`
  );
}

/**
 * 把后端出参铺成矩阵（对称、对角线自比）。
 *
 * 入参缺失 / 基金不足 2 只时返回空矩阵，**不抛异常**——展示增强不该让面板挂掉。
 */
export function buildCorrelationMatrix(
  data: HoldingCorrelationData | null | undefined
): CorrelationMatrix {
  const funds = data?.funds ?? [];
  const index = new Map<string, CorrelationCell>();
  for (const cell of data?.cells ?? []) {
    index.set(pairKeyOf(cell.fund_code_a, cell.fund_code_b), cell);
  }

  const rows: CorrelationRow[] = funds.map(rowFund => ({
    fund: rowFund,
    cells: funds.map(colFund =>
      buildCell(
        rowFund,
        colFund,
        index.get(pairKeyOf(rowFund.fund_code, colFund.fund_code))
      )
    )
  }));

  return {
    funds,
    rows,
    computedPairs: data?.computed_pairs ?? 0,
    totalPairs: data?.total_pairs ?? 0,
    truncatedCount: data?.truncated.count ?? 0,
    truncatedMarketValuePct: data?.truncated.market_value_pct ?? 0,
    coveragePct: 100 - (data?.truncated.market_value_pct ?? 0),
    coverageText: data ? coverageTextOf(data, funds) : "",
    window: data?.window ?? "",
    minOverlap: data?.min_overlap ?? 0
  };
}

/** 矩阵能否呈现：至少 2 只成员（1 只没有「两两」可言） */
export function canRenderCorrelation(matrix: CorrelationMatrix): boolean {
  return matrix.funds.length >= 2;
}

/** 「可算出比例」文案：卡面要求先给这个数，再谈结论 */
export function computedRatioText(matrix: CorrelationMatrix): string {
  if (!matrix.totalPairs) return "—";
  const pct = (matrix.computedPairs / matrix.totalPairs) * 100;
  return `${matrix.computedPairs}/${matrix.totalPairs}（${pct.toFixed(1)}%）`;
}

export interface CorrelationTally {
  /** 可算出的对数（各档之和） */
  ok: number;
  /** ρ ≥ 0.8：几乎同步（分散无效，优先看） */
  high: number;
  /** 0.5 ≤ ρ < 0.8：偏同向 */
  mid: number;
  /** ρ < −0.3：反向（天然对冲） */
  negative: number;
  /** 算不出的对数（三种原因合计） */
  unavailable: number;
}

/**
 * 对 cells 做分档计数（面板顶部的「一眼看结论」数字）。
 *
 * 只统计可算出的对，`unavailable` 单独一档——把算不出的并进「低相关」会让
 * 「没数据」看起来像「分散效果好」，这是最坏的一种误读。
 */
export function tallyCorrelation(cells: CorrelationCell[]): CorrelationTally {
  const tally: CorrelationTally = {
    ok: 0,
    high: 0,
    mid: 0,
    negative: 0,
    unavailable: 0
  };
  for (const cell of cells) {
    if (cell.status !== "ok" || cell.correlation === null) {
      tally.unavailable += 1;
      continue;
    }
    tally.ok += 1;
    const tone = correlationTone(cell.correlation);
    if (tone === "high") tally.high += 1;
    else if (tone === "mid") tally.mid += 1;
    else if (tone === "negative") tally.negative += 1;
  }
  return tally;
}
