/**
 * 持仓全景海报的数据模型（#1016）。
 *
 * 为什么把绘制数据抽成纯函数：canvas 绘制本身要 DOM，没法在 vitest 里直接跑；
 * 而海报最容易错的是「画了什么」——金额口径、占比分母、空档处理——不是像素。
 * 把这些判据压成不碰 DOM 的纯函数，单测就能钉住「海报说了什么」。
 *
 * 口径纪律（沿用全景页既有约定）：
 * - 金额一律人民币元（后端 *_cny 字段直出），不在此处换算；
 * - 占比分母 = Σ 分布项，与 `allocation_scope.denominator` 一致；分母为 0 时
 *   不画任何扇区，也不产生 NaN/Infinity（弱网/空账户下不能崩，见 #1016 验收）；
 * - 负债不进资产分布的分母。
 */

export interface PosterMoney {
  label: string;
  value: number;
  /** 是否按涨红跌绿着色（仅盈亏这类语义用；存量金额走中性色） */
  semantic?: "pnl";
}

export interface PosterSlice {
  label: string;
  value: number;
  color: string;
}

export interface PosterData {
  /** 海报主标题 */
  title: string;
  /** 生成日期（本地日期，YYYY-MM-DD），由调用方给，模块不读时钟 */
  date: string;
  /** 首屏金额区（总资产 / 净资产 / 总盈亏等） */
  figures: PosterMoney[];
  /** 资产大类分布（画成占比条） */
  slices: PosterSlice[];
  /** 页脚口径说明 */
  footnote: string;
}

/** 海报画布固定尺寸（CSS 像素）：宽度适配分享，高度按内容定死，避免按 min-height 解析带来的不确定高度。 */
export const POSTER_WIDTH = 750;
export const POSTER_HEIGHT = 1180;
export const POSTER_SCALE = 2; // 高清屏导出倍率，toDataURL 用

/**
 * 计算每个分布项的占比（0~100，保留一位小数）。
 *
 * 分母恒为 Σ value；任一 value 为负/非有限一律当 0（分布项不应为负，
 * 但脏数据不能让分母变负、把占比画成负数）。分母 <= 0 时全部返回 0。
 */
export function slicePercentages(values: number[]): number[] {
  const safe = values.map(v => (Number.isFinite(v) && v > 0 ? v : 0));
  const total = safe.reduce((s, v) => s + v, 0);
  if (total <= 0) {
    return safe.map(() => 0);
  }
  return safe.map(v => Math.round((v / total) * 1000) / 10);
}

/**
 * 金额格式化：海报里一律 ¥ + 千分位 + 两位小数。
 * 非有限值回退为 ¥0.00，避免 toDataURL 前出现 "NaN" 印在图上。
 */
export function formatYuan(value: number): string {
  const safe = Number.isFinite(value) ? value : 0;
  const sign = safe < 0 ? "-" : "";
  const [int, dec] = Math.abs(safe).toFixed(2).split(".");
  return `${sign}¥${int.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${dec}`;
}

/**
 * 从全景页已有的 distributions 构造海报数据。
 *
 * `category_distribution` 是资产大类（负债端不在此数组），直接可做占比条；
 * `total_assets/total_liabilities/net_worth/total_pnl` 走同一份后端口径，
 * 页面层不做二次减法（与 index.vue 的净资产约定一致）。
 */
export function buildPosterData(input: {
  date: string;
  totalAssets: number;
  totalLiabilities: number;
  netAssets: number;
  totalPnl: number;
  categories: Array<{ name: string; value: number }>;
  colors: string[];
}): PosterData {
  const categories = input.categories.filter(
    c => Number.isFinite(c.value) && c.value > 0
  );
  const slices: PosterSlice[] = categories.map((c, i) => ({
    label: c.name,
    value: c.value,
    color: input.colors[i % input.colors.length] || "#e34f38"
  }));

  return {
    title: "我的资产全景",
    date: input.date,
    figures: [
      { label: "总资产", value: input.totalAssets },
      { label: "净资产", value: input.netAssets },
      { label: "总负债", value: input.totalLiabilities },
      { label: "总盈亏", value: input.totalPnl, semantic: "pnl" }
    ],
    slices,
    footnote: "数据来自本地账本 · 占比按资产口径计算"
  };
}
