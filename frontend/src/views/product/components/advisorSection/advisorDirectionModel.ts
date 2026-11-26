import type { AdvisorStyleDirection } from "@/api/funds";

/**
 * 「与我账户的对照」·方向行的展示口径（纯函数，可单测）。
 *
 * 为什么单列：这一块的判据是「差多少算不一致」，属业务口径而非排版。写在
 * `<script setup>` 里只能用组件测试去钉，而它其实是两个数相减再比阈值——
 * 抽成纯函数后可以直接断言边界（4.9 不点、5.0 点）。
 */

/**
 * 差值达到这么多 pp 才判「方向不一致」。
 *
 * 5pp 的来历：四个方向的中位数差异在 2~3pp（用户真实账户实测），阈值再低会
 * 让五档全部点色，等于没有提示；再高则漏掉「中盘 17pp」之外的真差异。
 * 阈值只决定**要不要给视觉强调**，不改变数值本身。
 */
export const BIG_DIFF_PP = 5;

export interface DirectionRow {
  key: string;
  /** 组合占比(%) */
  adv: number;
  /** 我的占比(%) */
  mine: number;
  /** 我 − 组合（pp），保留 1 位——显示到 0.1pp 已超出估算精度 */
  diff: number;
  /** 是否达到 {@link BIG_DIFF_PP}，用于点色 */
  big: boolean;
}

/**
 * 把两侧的方向占比配成行。
 *
 * 以**组合侧**的方向为骨架（后端两侧都返回同一套五方向，缺哪个都补 0）：
 * 少一个方向的行会让「中盘 vs 固收」的对照错位，比缺行更糟。
 * 空骨架（组合没有快照）时返回空数组，由调用方整块降级。
 */
export function buildDirectionRows(
  adv: readonly AdvisorStyleDirection[] | undefined,
  mine: readonly AdvisorStyleDirection[] | undefined
): DirectionRow[] {
  if (!adv?.length) return [];
  const mineMap = new Map((mine ?? []).map(d => [d.key, d.value]));
  return adv.map(d => {
    const mineValue = mineMap.get(d.key) ?? 0;
    const diff = Math.round((mineValue - d.value) * 10) / 10;
    return {
      key: d.key,
      adv: d.value,
      mine: mineValue,
      diff,
      big: Math.abs(diff) >= BIG_DIFF_PP
    };
  });
}

/**
 * 差异最大的 N 档（用于提示条）。
 *
 * **只点最不一致的两档**：三档以上会变成「五档里四档都不同」的废话，
 * 而用户需要的是一个能立刻抓住的结构性差异。并列时保持原顺序（稳定）。
 */
export function mostDivergent(
  rows: readonly DirectionRow[],
  count = 2
): DirectionRow[] {
  return [...rows]
    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))
    .slice(0, count);
}

/**
 * 提示条里单档的措辞：**高的一侧在前**。
 *
 * 「我 32.30% · 组合 8.80%」比「组合 8.80% · 我 32.30%」更快读出结构差异——
 * 但两支绝对值相等时不加判断，按「组合 · 我」原序（避免凭 0.04pp 决定叙述顺序）。
 */
export function divergenceText(row: DirectionRow): string {
  const adv = `${row.adv.toFixed(2)}%`;
  const mine = `${row.mine.toFixed(2)}%`;
  return row.mine > row.adv
    ? `我 ${mine} · 组合 ${adv}`
    : `组合 ${adv} · 我 ${mine}`;
}

/** 差值文案：正数显式带「+」，0 不带符号（`0.0` 而不是 `+0.0`） */
export function diffText(diff: number): string {
  // 先取到显示精度再判零：`-0.04` 直接判零不成立，但 `(-0.04).toFixed(1)`
  // 会输出「-0.0」——一个既不等于 0 又显示为 0 的符号，读起来像跌了一点点
  const rounded = Math.round(diff * 10) / 10;
  if (rounded === 0) return "0.0";
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)}`;
}

/**
 * 双条形的刻度分母：两侧实测最大值。
 *
 * **不用固定 100%**：五方向的实测最大值在 35% 上下（真实库 ZH012926），
 * 按 100 画全是短条，读不出「哪一档更重」。取下限 1 防止空数据时除零
 * （空骨架已被调用方拦掉，这里只是兜底）。
 */
export function barScaleOf(rows: readonly DirectionRow[]): number {
  const max = rows.reduce((acc, row) => Math.max(acc, row.adv, row.mine), 0);
  return Math.max(max, 1);
}

/** 条形宽度（%）：按刻度归一，最小 1% 保证「有一点」看得见 */
export function barWidthPct(value: number, scale: number): string {
  return `${Math.max((value / scale) * 100, 1).toFixed(1)}%`;
}
