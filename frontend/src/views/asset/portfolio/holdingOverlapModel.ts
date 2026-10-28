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
  /** 判为「配置重复」的基金对数（不含份额重复，也不含弱提醒档） */
  duplicate_count: number;
  /** 弱提醒条数（`low` + `trivial`），与折叠区里列出的条数一致 */
  weak_count: number;
  /** 金额分档线（分），弱提醒区文案里的「不足 ¥X」用它，不在前端另写一个数 */
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
 * 把后端的 `overlap_level` 翻成标签（只用于「要点」列表）。
 *
 * `low` / `trivial` 返回 null：它们不进要点列表，而是统一收进「弱提醒」区，
 * 由区块标题与 `弱提醒` 标签表达档位——在要点列表里给它们贴标签，
 * 等于把已经被分档过滤掉的噪音重新贴回来。
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

/** 「要点」档位：进主列表，值得处置或至少值得知道 */
const PRIMARY_LEVELS: OverlapLevel[] = ["duplicate", "watch", "same-series"];

/** 每页展示多少条弱提醒——1834 对一次渲染会让标签页直接卡住 */
export const WEAK_PAGE_SIZE = 50;

export interface OverlapPairSplit {
  /** 主列表：配置重复 / 需留意 / 同一基金不同份额 */
  primary: OverlapPair[];
  /** 弱提醒：`low`（比例未达线）+ `trivial`（金额不足），默认折叠但**可见** */
  weak: OverlapPair[];
}

/**
 * 把 pairs 拆成「要点」与「弱提醒」两堆。
 *
 * 为什么弱提醒既不能删也不能混进要点：真实组合里 96 只基金能配出 1800+ 对，
 * 绝大多数是观察仓之间的几毛钱重叠（实测 1834 对里金额中位数 ¥0.68）。
 * 混进主列表 → 噪音淹没真重复；直接丢掉 → 用户以为系统没算到（他明明买了重复的基金）。
 * 所以是**分档**：要点直接列，弱提醒折叠可展开。
 * 后端已按档位排好序，这里只做切分，不重排。
 */
export function splitOverlapPairs(
  data: HoldingOverlapData | null | undefined
): OverlapPairSplit {
  const pairs = data?.pairs ?? [];
  const primary: OverlapPair[] = [];
  const weak: OverlapPair[] = [];
  for (const pair of pairs) {
    (PRIMARY_LEVELS.includes(pair.overlap_level) ? primary : weak).push(pair);
  }
  return { primary, weak };
}

/**
 * 一对基金的稳定 key（列表渲染 / 明细展开共用）。
 *
 * 用代码而不是名称：同一基金不同份额的名称会变（「A」「C」后缀），代码不会；
 * 也不用 index——筛选后 index 会串位，展开状态会跟错行。
 */
export function pairKey(pair: OverlapPair): string {
  return `${pair.fund_code_a}-${pair.fund_code_b}`;
}

/** 汇总用的四类计数（互斥，加起来等于 pairs 长度） */
export interface OverlapTally {
  duplicate: number;
  watch: number;
  sameSeries: number;
  weak: number;
}

export type OverlapTallyKey = keyof OverlapTally;

export interface OverlapTallyChip {
  key: OverlapTallyKey;
  label: string;
  count: number;
  /** 数字的语义色：danger 红 / warning 橙 / info 蓝 / muted 灰 */
  tone: "danger" | "warning" | "info" | "muted";
}

/**
 * 按档位统计对数。
 *
 * **四类必须互斥**：如果「弱提醒」被并进「配置重复」，第一屏的 N 就会是假的
 * （用户会去找那 N 对，却发现一千多对只是观察仓）；反过来，「同一基金不同份额」
 * 也不是配置重复——那是买了两次同一只基金。所以这里逐对归类，不重复计数。
 *
 * 计数从 `pairs` 现算而不是读 `duplicate_count` / `weak_count`：页面渲染的就是
 * `pairs`，两个来源一旦漂移，就会出现「标题说 10 对、列表只有 9 对」。
 */
export function tallyOverlap(
  data: HoldingOverlapData | null | undefined
): OverlapTally {
  const tally: OverlapTally = {
    duplicate: 0,
    watch: 0,
    sameSeries: 0,
    weak: 0
  };
  for (const pair of data?.pairs ?? []) {
    switch (pair.overlap_level) {
      case "duplicate":
        tally.duplicate += 1;
        break;
      case "watch":
        tally.watch += 1;
        break;
      case "same-series":
        tally.sameSeries += 1;
        break;
      default:
        tally.weak += 1;
    }
  }
  return tally;
}

/**
 * 汇总条要展示的 chip（只给非零项）。
 *
 * 用 chip 而不是一句话：四个数字并排，用户一眼就能分出「要处理的 10 对」
 * 和「可以不管的 1817 对」；长句子在窄屏会折成三行，读起来像免责声明。
 */
export function describeOverlapTally(
  data: HoldingOverlapData | null | undefined
): OverlapTallyChip[] {
  const tally = tallyOverlap(data);
  const chips: OverlapTallyChip[] = [
    {
      key: "duplicate",
      label: "配置重复",
      count: tally.duplicate,
      tone: "danger"
    },
    { key: "watch", label: "需留意", count: tally.watch, tone: "warning" },
    {
      key: "sameSeries",
      label: "同一基金份额",
      count: tally.sameSeries,
      tone: "info"
    },
    { key: "weak", label: "弱提醒", count: tally.weak, tone: "muted" }
  ];
  return chips.filter(chip => chip.count > 0);
}

/**
 * 弱提醒区的说明文案。
 *
 * 必须同时交代「为什么被降档」和「怎么看到全部」：只说「都是小仓位」会让用户
 * 以为系统把它们藏了；只说「默认折叠」又不解释折叠的原因。
 */
export function describeWeakHint(gateText: string): string {
  return (
    `重复投入不足 ${gateText}，或重合度还没到「需留意」的线，多为观察仓。` +
    "默认折叠但仍可查看：展开后可筛选基金、逐对查看共同重仓股。"
  );
}

/**
 * 弱提醒条目的一句话解释。
 *
 * 后端对 `low` 不下发理由（它原本不占版面，写理由是浪费），但弱提醒区里每条
 * 都得说清「为什么在这里」——否则用户看到一条没有理由的「弱提醒」只会困惑。
 */
export function describeWeakReason(
  pair: OverlapPair | null | undefined
): string {
  if (!pair) return "";
  if (pair.overlap_reason) return pair.overlap_reason;
  return `重合 ${pair.weighted_overlap.toFixed(1)}%，未达「需留意」的仓位线`;
}

/**
 * 按关键词筛弱提醒（基金代码或名称）。
 *
 * 1817 对里找一个特定的基金，靠滚动是不现实的。筛选只做包含匹配、大小写不敏感：
 * 用户输入「白酒」「012414」都能命中，不需要教他正则。
 */
export function filterWeakPairs(
  pairs: OverlapPair[],
  keyword: string
): OverlapPair[] {
  const needle = keyword.trim().toLowerCase();
  if (!needle) return pairs;
  return pairs.filter(pair =>
    [
      pair.fund_code_a,
      pair.fund_code_b,
      pair.fund_name_a,
      pair.fund_name_b
    ].some(field =>
      String(field ?? "")
        .toLowerCase()
        .includes(needle)
    )
  );
}

export interface WeakPairPage {
  visible: OverlapPair[];
  /** 还没展示的条数 */
  remaining: number;
  hasMore: boolean;
}

/**
 * 弱提醒分页（按已加载条数切片）。
 *
 * 不用「展开全部」：1817 条 DOM 会让标签页僵住几秒。分页 + 明确剩余条数，
 * 用户想找的基金靠筛选，而不是靠翻完 1817 条。
 */
export function sliceWeakPairs(
  pairs: OverlapPair[],
  loaded: number
): WeakPairPage {
  const limit = Math.max(0, loaded);
  const visible = pairs.slice(0, limit);
  const remaining = Math.max(0, pairs.length - visible.length);
  return { visible, remaining, hasMore: remaining > 0 };
}

/** 口径声明（后端下发，原样展示）：空串项一律滤掉，避免渲染出空行 */
export function describeCaveats(
  data: HoldingOverlapData | null | undefined
): string[] {
  return (data?.caveats ?? []).filter(
    text => typeof text === "string" && text.trim().length > 0
  );
}
