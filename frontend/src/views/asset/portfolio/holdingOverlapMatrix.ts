/**
 * 组合内基金两两重叠矩阵（#2686）。
 *
 * 为什么矩阵需要后端单独下发 `funds`：`pairs` 只含**有重叠**的基金对，直接拿它铺格子，
 * 三只基金只有一对重叠时就只剩 2 个格子，另外两只「确实不重叠」的基金凭空消失——
 * 用户看到的是「我的基金互不相干」，而真实的结论是「这几只确实无关，但那两只高度重合」。
 *
 * 六种格子形态（**不可合并**，合并就会给出错误安心）：
 * - `self` 自比（对角线）：「—」，不是 100%；
 * - `none` 有资格比较、确实零共同重仓股：「0%」；
 * - `low` / `mid` / `high` 后端判定的档位（`low`+`trivial`+`same-series` / `watch` /
 *   `duplicate`）—— 档位阈值只在后端定义，前端不二次推导；
 * - `incomparable` **披露口径不同**（半年报全量 vs 季报前十大）：「不可比」，不是 0%
 *   —— 混算会系统性低估重叠，把「不可比」显示成 0% 正是 #2604 要挡的那种错误安心。
 */

import type {
  HoldingOverlapData,
  OverlapFund,
  OverlapPair
} from "@/api/holdingOverlap";
import { formatWeightedOverlap } from "./holdingOverlapModel";

export type MatrixCellTone =
  "self" | "none" | "low" | "mid" | "high" | "incomparable";

export interface MatrixCell {
  /** 格子里的文字：百分比 / `—`（自比）/ `0%` / `不可比` */
  text: string;
  tone: MatrixCellTone;
  /** 悬停说明：这个数字为什么是这样（尤其「不可比」必须解释原因） */
  title: string;
}

export interface MatrixRow {
  fund: OverlapFund;
  cells: MatrixCell[];
}

export interface OverlapMatrix {
  /** 参与展示的基金（市值降序；已按上限截断） */
  funds: OverlapFund[];
  rows: MatrixRow[];
  /** 超出上限被折叠的只数（0 = 全量展示） */
  truncated: number;
}

/**
 * 矩阵上限：卡内实测真实组合 ≤ 8 只，12 只是安全边界。
 * 上限存在的意义不是省 DOM，而是避免「大组合铺成 96×96」这种读不出结论的视图。
 */
export const MATRIX_MAX_FUNDS = 12;

/** 后端档位 → 矩阵三档视觉（`low` 档包含 same-series / trivial，都是弱提醒） */
const LEVEL_TONE: Record<OverlapPair["overlap_level"], MatrixCellTone> = {
  duplicate: "high",
  watch: "mid",
  "same-series": "low",
  low: "low",
  trivial: "low"
};

/** 无序基金对的键：矩阵是对称的，不区分 a/b 顺序 */
function pairKeyOf(codeA: string, codeB: string): string {
  return [codeA, codeB].sort().join("|");
}

function indexPairs(pairs: OverlapPair[]): Map<string, OverlapPair> {
  const index = new Map<string, OverlapPair>();
  for (const pair of pairs) {
    index.set(pairKeyOf(pair.fund_code_a, pair.fund_code_b), pair);
  }
  return index;
}

function buildCell(
  rowFund: OverlapFund,
  colFund: OverlapFund,
  pair: OverlapPair | undefined
): MatrixCell {
  if (rowFund.fund_code === colFund.fund_code) {
    return { text: "—", tone: "self", title: "同一只基金，不参与比较" };
  }
  // 口径不同优先于「无重叠」：这类对后端根本不计算，显示 0% 就是造假
  if ((rowFund.basis ?? "") !== (colFund.basis ?? "")) {
    return {
      text: "不可比",
      tone: "incomparable",
      title: `披露口径不同（${rowFund.basis || "未知"} vs ${colFund.basis || "未知"}），混算会低估重叠，故不比较`
    };
  }
  if (!pair) {
    return { text: "0%", tone: "none", title: "没有共同重仓股" };
  }
  return {
    text: formatWeightedOverlap(pair.weighted_overlap),
    tone: LEVEL_TONE[pair.overlap_level] ?? "low",
    title:
      pair.overlap_reason ||
      `共同重仓 ${pair.common_holdings.length} 只，加权 ${formatWeightedOverlap(pair.weighted_overlap)}`
  };
}

/**
 * 把后端出参铺成矩阵。
 *
 * 入参缺失 / 基金不足 2 只时返回空矩阵（调用方据此回退到列表视图），**不抛异常**——
 * 这是个展示增强，不该让整个面板挂掉。
 */
export function buildOverlapMatrix(
  data: HoldingOverlapData | null | undefined,
  maxFunds: number = MATRIX_MAX_FUNDS
): OverlapMatrix {
  const all = data?.funds ?? [];
  const limit = Math.max(0, maxFunds);
  const funds = all.slice(0, limit);
  const index = indexPairs(data?.pairs ?? []);
  const rows: MatrixRow[] = funds.map(rowFund => ({
    fund: rowFund,
    cells: funds.map(colFund =>
      buildCell(
        rowFund,
        colFund,
        index.get(pairKeyOf(rowFund.fund_code, colFund.fund_code))
      )
    )
  }));
  return { funds, rows, truncated: Math.max(0, all.length - funds.length) };
}

/** 矩阵能否呈现：至少 2 只可比基金（1 只没有「两两」可言） */
export function canRenderMatrix(matrix: OverlapMatrix): boolean {
  return matrix.funds.length >= 2;
}
