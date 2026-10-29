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
 *
 * ## 为什么 `same-series` 不另造一种颜色，而是加「※」角标
 *
 * 卡面验收要求「同一基金不同份额有**独立标记**，不与 `duplicate` 同色：否则用户会去卖
 * 本来正常持有的份额」。
 *
 * - **颜色不能分**：同一基金不同份额的重叠比例天然接近 100%，但它是**伪重复**——占比
 *   再高也不该提示「配置重复」。它的数值档位只能落在 `low`（弱提醒），硬给它一个色阶
 *   会让「低档」出现两种颜色，读图的人无从判断哪个才要看。
 * - **标记必须独立**：光靠 `low` 档的颜色，用户会以为它是「重叠度低」，而真相是
 *   「这两格压根不是两只基金」。故在格子右上角加 `※`、并在图例写明含义——颜色说
 *   「不用管」，角标说「为什么不用管」。
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
  /**
   * 同一只基金的不同份额（后端 `overlap_level='same-series'`）。
   *
   * 与 `tone` 正交：`tone` 说的是「这个数该不该管」，本字段说的是「这两格算不算两只
   * 基金」。占比可能 100%，但结论是「不用管」，所以它是弱提醒色 + 独立角标。
   */
  sameSeries: boolean;
  /** 悬停说明：这个数字为什么是这样（尤其「不可比」必须解释原因） */
  title: string;
}

export interface MatrixRow {
  fund: OverlapFund;
  cells: MatrixCell[];
}

export interface OverlapMatrix {
  /** 参与展示的基金（市值降序；后端已按覆盖规则截断） */
  funds: OverlapFund[];
  rows: MatrixRow[];
  /** 按覆盖规则被折叠的只数（0 = 全量展示） */
  truncatedCount: number;
  /**
   * 被折叠部分占总市值的百分比（0 = 没有未覆盖部分，或市值不可用）。
   *
   * 必须与矩阵同屏显示：「只展开 20 只」在小组合里等于全量，在分散组合里可能只代表
   * 六成仓位——不写出来，用户会把「已展开部分」的结论当成整体结论。
   */
  truncatedMarketValuePct: number;
}

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
    return {
      text: "—",
      tone: "self",
      sameSeries: false,
      title: "同一只基金，不参与比较"
    };
  }
  // 口径不同优先于「无重叠」：这类对后端根本不计算，显示 0% 就是造假
  if ((rowFund.basis ?? "") !== (colFund.basis ?? "")) {
    return {
      text: "不可比",
      tone: "incomparable",
      sameSeries: false,
      title: `披露口径不同（${rowFund.basis || "未知"} vs ${colFund.basis || "未知"}），混算会低估重叠，故不比较`
    };
  }
  if (!pair) {
    return {
      text: "0%",
      tone: "none",
      sameSeries: false,
      title: "没有共同重仓股"
    };
  }
  const sameSeries = pair.overlap_level === "same-series";
  const amountText = `共同重仓 ${pair.common_holdings.length} 只，加权 ${formatWeightedOverlap(pair.weighted_overlap)}`;
  return {
    text: formatWeightedOverlap(pair.weighted_overlap),
    tone: LEVEL_TONE[pair.overlap_level] ?? "low",
    sameSeries,
    // same-series 的说明必须自带含义：不能指望后端 reason 的措辞永远提到「份额」，
    // 否则角标就成了一个没有解释的符号（用户会当成「重要」而不是「不用管」）
    title: sameSeries
      ? `同一只基金的不同份额，持仓完全相同，不算配置重复（${pair.overlap_reason || amountText}）`
      : pair.overlap_reason || amountText
  };
}

/**
 * 把后端出参铺成矩阵。
 *
 * 成员**不由前端截断**：后端按「累计市值覆盖 ≥90%、上限 20、下限 8」裁好放在
 * `matrix.funds`（`services/matrix_members.py`，与相关性矩阵共用）。前端若自己再截
 * 一次，两张矩阵就可能在同一個组合上给出不同的行列——「切换视图少了 8 只」比
 * 「矩阵格子多一点」难解释得多。
 *
 * 入参缺失 / 基金不足 2 只时返回空矩阵（调用方据此回退到列表视图），**不抛异常**——
 * 这是个展示增强，不该让整个面板挂掉。
 */
export function buildOverlapMatrix(
  data: HoldingOverlapData | null | undefined
): OverlapMatrix {
  // 旧响应没有 `matrix`（回滚 / 缓存）：退回全量成员，宁可格子多也不凭空少行
  const members = data?.matrix?.funds?.length
    ? data.matrix.funds
    : (data?.funds ?? []);
  const index = indexPairs(data?.pairs ?? []);
  const rows: MatrixRow[] = members.map(rowFund => ({
    fund: rowFund,
    cells: members.map(colFund =>
      buildCell(
        rowFund,
        colFund,
        index.get(pairKeyOf(rowFund.fund_code, colFund.fund_code))
      )
    )
  }));
  return {
    funds: members,
    rows,
    truncatedCount: data?.matrix?.truncated_count ?? 0,
    truncatedMarketValuePct: data?.matrix?.truncated_market_value_pct ?? 0
  };
}

/** 矩阵能否呈现：至少 2 只可比基金（1 只没有「两两」可言） */
export function canRenderMatrix(matrix: OverlapMatrix): boolean {
  return matrix.funds.length >= 2;
}
