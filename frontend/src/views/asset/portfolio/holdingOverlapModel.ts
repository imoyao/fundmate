/**
 * 组合内基金持仓重叠度面板的派生逻辑（#2604）。
 *
 * 提到纯模块的原因与 `views/asset/family/familyMemberModel.ts` 相同：vitest 的 node
 * 环境拉不起渲染器（会连带 router / supabase），组件里可测的判定必须落在这里。
 *
 * **本模块存在的唯一理由是把「没有重叠」的三种成因分开**：
 * 1. `degraded` —— 取数失败，显示「暂时取不到」；
 * 2. `fund_count < 2` —— 可比基金不足 2 只，**算不出**（不是「不重叠」）；
 * 3. `fund_count >= 2` 且 pairs 为空 —— 算出来了，结论就是**确实不重叠**。
 *
 * 把这三种都渲染成「重叠 0%」是**错误安心**：用户会以为已经查过、结果是零重合。
 */

/** 共同重仓股明细 */
export interface OverlapCommonHolding {
  stock_code: string;
  /** 名称只作展示（同一只股票在不同基金里的写法可能不同） */
  stock_name: string;
  ratio_a: number;
  ratio_b: number;
  min_ratio: number;
}

/** 一对有重叠的基金 */
export interface OverlapPair {
  fund_code_a: string;
  fund_name_a: string;
  report_period_a: string;
  fund_code_b: string;
  fund_name_b: string;
  report_period_b: string;
  /** 披露口径：full=半年报/年报全量，top10=季报前十大 */
  holding_basis: string;
  /** 集合口径重叠度（0~1） */
  jaccard: number;
  /** 加权口径重叠度（百分点），按共同持仓的 min(占净值比例) 求和 */
  weighted_overlap: number;
  /**
   * 重复投入金额（分）：Σ min(持仓市值A × 占比A, 持仓市值B × 占比B)。
   * 这是「这笔重复真正压了多少钱」，与 `weighted_overlap` 是两件事——
   * 后者只说两只基金像不像，前者才回答「值不值得管」。
   */
  overlap_amount_cents: number;
  /** 后端按双口径阈值定性，前端不二次推导 */
  overlap_level: OverlapLevel;
  /** 触发原因说明（`low` 时为空串；`trivial` 说明为什么没提示） */
  overlap_reason: string;
  common_holdings: OverlapCommonHolding[];
}

/**
 * 重叠定性（后端 `_classify_overlap` + `_apply_amount_gate` 判定）：
 * `duplicate` 配置重复 / `watch` 需留意 / `low` 一般 /
 * `same-series` 同一只基金的不同份额（份额重复，非配置重复）/
 * `trivial` 比例可能很高，但重复投入金额低于提示线（观察仓，不提示）。
 */
export type OverlapLevel =
  "duplicate" | "watch" | "low" | "same-series" | "trivial";

/** 无持仓明细的持仓 */
export interface OverlapUncovered {
  symbol: string;
  name: string;
  market_value_cents: number;
}

/** 重叠度接口出参 */
export interface HoldingOverlapData {
  pairs: OverlapPair[];
  /** 参与计算的基金数 */
  fund_count: number;
  /** 因披露口径不同被跳过的对数 */
  skipped_basis_mismatch: number;
  /** 因占比缺失被排除的持仓行数 */
  skipped_null_ratio: number;
  total_market_value_cents: number;
  /** 有持仓明细的基金市值 / 全部持仓市值 * 100 */
  coverage_pct: number;
  uncovered: OverlapUncovered[];
  /** 判为「配置重复」的基金对数（不含份额重复，也不含金额不足未提示的） */
  duplicate_count: number;
  /** 被金额闸门挡下的对数（比例可能很高，但重复的只是几毛钱） */
  trivial_count: number;
  /** 金额提示线（分），文案里的「不足 ¥X 未提示」用它，不在前端另写一个数 */
  min_overlap_amount_cents: number;
  /** 口径声明（持仓快照滞后 / 高换手失真 / 金额为保守下界） */
  caveats: string[];
  /** 取数失败时为 true */
  degraded: boolean;
  source: string;
}

export type OverlapPanelState =
  "degraded" | "not-computable" | "no-overlap" | "has-pairs";

/** 面板状态判定：三种「没有重叠」的成因必须分开 */
export function resolveOverlapPanelState(
  data: HoldingOverlapData | null | undefined
): OverlapPanelState {
  if (!data || data.degraded) return "degraded";
  if ((data.fund_count ?? 0) < 2) return "not-computable";
  if (!data.pairs || data.pairs.length === 0) return "no-overlap";
  return "has-pairs";
}

/** 加权重叠度格式化（百分点） */
export function formatWeightedOverlap(
  value: number | null | undefined
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  // 后端只保留 weighted_overlap > 0 的对，但 0.04 这类极小值 toFixed(1) 会渲染成
  // 「0.0%」——列在「有重叠」里却显示 0%，既自相矛盾，也会让人怀疑整列数值。
  // 显示下限比假精确有用：真为 0 的对后端根本不会下发。
  if (value > 0 && value < 0.05) return "<0.1%";
  return `${value.toFixed(1)}%`;
}

/** 集合口径重叠度格式化（0~1 → 百分比） */
export function formatJaccard(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(0)}%`;
}

/** 千分位（不用 toLocaleString：vitest 的 node 环境与浏览器 ICU 可能不一致） */
function groupThousands(int: number): string {
  return String(int).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * 重复投入金额格式化（分 → ¥）。
 *
 * 小额必须保留两位：「¥0.46」才能说明这是一笔观察仓；四舍五入成「¥0」会让人
 * 以为是取数缺失。≥1 元后取整——精确到分对「值不值得管」这个判断没有帮助。
 */
export function formatAmountCents(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const yuan = value / 100;
  if (yuan < 0) return "—";
  if (yuan === 0) return "¥0";
  if (yuan < 1) return `¥${yuan.toFixed(2)}`;
  return `¥${groupThousands(Math.round(yuan))}`;
}

/** 披露口径的中文名 */
export function describeBasis(basis: string | null | undefined): string {
  if (basis === "full") return "半年报/年报全量";
  if (basis === "top10") return "季报前十大";
  return basis || "口径未知";
}

/**
 * 报告期错配的提示。
 * 两只基金的报告期不同时，重叠度天然带时点差——必须让用户知道，
 * 否则「62% 重叠」会被当成同一时点的精确结论。
 */
export function describePeriodMismatch(
  pair: OverlapPair | null | undefined
): string {
  if (!pair) return "";
  if (pair.report_period_a === pair.report_period_b) return "";
  return `报告期不同（${pair.report_period_a} / ${pair.report_period_b}），重叠度带时点差`;
}

/** 覆盖率说明文案 */
export function describeCoverage(
  data: HoldingOverlapData | null | undefined
): string {
  const pct = data?.coverage_pct ?? 0;
  const n = data?.fund_count ?? 0;
  return `持仓明细覆盖 ${pct.toFixed(1)}%，${n} 只基金参与比较`;
}

/** 口径跳过说明：披露口径不同的基金对没有比较，必须如实说 */
export function describeSkipped(
  data: HoldingOverlapData | null | undefined
): string {
  const basis = data?.skipped_basis_mismatch ?? 0;
  const nullRatio = data?.skipped_null_ratio ?? 0;
  const parts: string[] = [];
  if (basis > 0) {
    parts.push(`${basis} 对因披露口径不同（半年报全量 vs 季报前十大）未比较`);
  }
  if (nullRatio > 0) {
    parts.push(`${nullRatio} 条持仓因占比缺失未计入`);
  }
  return parts.join("；");
}

/** 重叠定性的展示标签 */
export interface OverlapLevelBadge {
  label: string;
  /** element-plus el-tag 的 type */
  tone: "danger" | "warning" | "info";
}

/**
 * 把后端的 `overlap_level` 翻成标签。
 *
 * `low` / `trivial` 返回 null（不占版面）：`low` 是「比例不够」，`trivial` 是
 * 「比例可能很高但只重复了几毛钱」——提示它们等于把噪音重新贴回列表。
 * `same-series` **不得**显示成「配置重复」——同一只基金的 A/C 份额持仓逐行相同，
 * 算出来必然是 100% 重叠，但它不是「两只基金买重了」，标错会让用户去卖本来正常持有的份额。
 */
export function describeOverlapLevel(
  pair: OverlapPair | null | undefined
): OverlapLevelBadge | null {
  if (!pair) return null;
  switch (pair.overlap_level) {
    case "duplicate":
      return { label: "配置重复", tone: "danger" };
    case "watch":
      return { label: "需留意", tone: "warning" };
    case "same-series":
      return { label: "同一基金不同份额", tone: "info" };
    default:
      return null;
  }
}

/** 被判为「同一只基金不同份额」的对数（份额重复，不计入配置重复） */
export function countSameSeriesPairs(
  data: HoldingOverlapData | null | undefined
): number {
  return (data?.pairs ?? []).filter(
    pair => pair.overlap_level === "same-series"
  ).length;
}

/**
 * 配置重复的汇总文案。
 *
 * 三种「看着重复」必须分开说：真·配置重复（不同基金重仓撞车）值得处置；
 * 同一基金的不同份额只是买了两次同一只基金；而**重复金额不足提示线**的那些
 * （一只基金只投了几块钱的观察仓）如果混进「N 对重复」，这个数字就是假的——
 * 用户会去找那 N 对，却发现一部分根本不用管。
 */
export function describeDuplicateSummary(
  data: HoldingOverlapData | null | undefined
): string {
  const parts: string[] = [];
  const duplicates = data?.duplicate_count ?? 0;
  const sameSeries = countSameSeriesPairs(data);
  const trivial = data?.trivial_count ?? 0;
  if (duplicates > 0) {
    parts.push(`检出 ${duplicates} 对配置重复（两只基金重仓高度重合）`);
  }
  if (sameSeries > 0) {
    parts.push(`${sameSeries} 对是同一基金的不同份额，不计入重复`);
  }
  if (trivial > 0) {
    const gate = formatAmountCents(data?.min_overlap_amount_cents);
    parts.push(`${trivial} 对重复投入不足 ${gate}，不计入提示`);
  }
  if (!parts.length) return "";
  return `${parts.join("；")}。`;
}

/** 值得占据版面的档位：其余（`low` / `trivial`）默认折叠 */
const HIGHLIGHT_LEVELS: OverlapLevel[] = ["duplicate", "watch", "same-series"];

/** 展开折叠区时最多渲染多少对——1834 对全渲染会让标签页直接卡住 */
export const FOLDED_PAGE_SIZE = 50;

export interface OverlapPairSplit {
  /** 默认展示的「要点」：真需要处置的档位 */
  highlighted: OverlapPair[];
  /** 默认折叠的对（`low` / `trivial`），展开时才有用 */
  folded: OverlapPair[];
  /** 折叠了多少对 */
  foldedCount: number;
}

/**
 * 把 pairs 拆成「要点」与「折叠」两堆。
 *
 * 为什么必须折叠：真实组合里 96 只基金能配出 1800+ 对，其中绝大多数是
 * 观察仓之间的几毛钱重叠（实测 1834 对里金额中位数 ¥0.68、过 ¥1,000 闸门的
 * 只有 16 对）。全部渲染既拖慢页面，也让真正的重复淹没在噪音里。
 * 后端已按档位排好序，这里只做切分，不重排。
 */
export function splitOverlapPairs(
  data: HoldingOverlapData | null | undefined
): OverlapPairSplit {
  const pairs = data?.pairs ?? [];
  const highlighted: OverlapPair[] = [];
  const folded: OverlapPair[] = [];
  for (const pair of pairs) {
    (HIGHLIGHT_LEVELS.includes(pair.overlap_level) ? highlighted : folded).push(
      pair
    );
  }
  return { highlighted, folded, foldedCount: folded.length };
}

/**
 * 展开时只取前 `pageSize` 对折叠项。
 *
 * 折叠区在真实数据里是四位数：全量渲染 = 几千个 `<li>` 加持仓标签，点击「显示全部」
 * 时标签页会僵住几秒。截断并如实告知「还有多少没显示」，比假装能全看更有用。
 */
export function pageFoldedPairs(
  folded: OverlapPair[],
  pageSize: number = FOLDED_PAGE_SIZE
): { visible: OverlapPair[]; hiddenCount: number } {
  const limited = folded.slice(0, Math.max(0, pageSize));
  return { visible: limited, hiddenCount: folded.length - limited.length };
}

export interface FoldHintInput {
  /** 是否已展开折叠区 */
  expanded: boolean;
  /** 折叠了多少对 */
  foldedCount: number;
  /** 展开后实际渲染了多少对 */
  visibleCount: number;
  /** 展开后仍被截断的有多少对 */
  hiddenCount: number;
  /** 金额提示线文案（后端下发，已格式化） */
  gateText: string;
}

/**
 * 折叠区的说明文案。
 *
 * 两个数字都不能省：不展开时说「折了多少对」，展开后必须说「还有多少对没显示」——
 * 只写「已展开」会让用户以为看到的就是全部，而截断只是为了性能。
 */
export function describeFoldHint(input: FoldHintInput): string {
  if (!input.expanded) {
    return `另有 ${input.foldedCount} 对未达提示线（比例不够，或重复投入不足 ${input.gateText}），已折叠`;
  }
  const base = `已展开前 ${input.visibleCount} 对未达提示线的重叠`;
  if (input.hiddenCount <= 0) return base;
  return `${base}，另有 ${input.hiddenCount} 对金额更低的未显示`;
}

/** 口径声明（后端下发，原样展示）：空串项一律滤掉，避免渲染出空行 */
export function describeCaveats(
  data: HoldingOverlapData | null | undefined
): string[] {
  return (data?.caveats ?? []).filter(
    text => typeof text === "string" && text.trim().length > 0
  );
}
