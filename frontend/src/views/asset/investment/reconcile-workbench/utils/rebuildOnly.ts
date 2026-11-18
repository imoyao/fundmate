/**
 * 「这条差异的唯一入口不在核对差异里」的判据（纯函数，无 Vue 依赖，可单测）。
 *
 * ## 为什么需要它
 *
 * 一条 `orphan` 差异说的是「账上有流水、系统里没有这只标的的持仓行」，它的唯一修法是
 * 域 F 的「按流水重建持仓」。可核对差异里那行的动作是「补充这笔」——当持仓行**真的
 * 不存在**时，补录必然在最后一步失败（后端 `_resolve_sell_position_id` 找不到持仓 →
 * 400「找不到这笔持仓：……去「修正数据」按流水重建」）。
 *
 * 于是同一条数据有两个入口：一个能修、一个走两步后被拦下并把人指回前一个。
 * 按「一个数据只有一个唯一可用入口」，**被域 F 分组覆盖的差异从核对差异里剔除**，
 * 只在修正数据里出现。
 *
 * ## 为什么按业务键覆盖判定，而不是「凡 orphan 都剔除」
 *
 * 真库实测（2026-11-14）188 条 pending orphan 里 180 条被悬空组覆盖、8 条没有：
 * 那 8 条的持仓行**还在**（`ownership_status='cleared'`、份额 0），只是份额与流水不符。
 * 它们补录得通，属于核对差异该管的事；一刀切剔除等于把 8 条真差异藏起来。
 *
 * 键与后端分组键同源（`f'{ledger_id}|{symbol}'`，见 `dangling_ref_service._build_group`），
 * 两侧都从同一条流水的 `(ledger_id, symbol)` 字面量来，不做归一化——归一化会把
 * 「同一代码两种写法」也算成覆盖，而那种情况本来就该由对账判成数量差异。
 */

import type { DanglingRefList, DiscrepancyItem } from "@/api/reconciliation";

/** 业务键：与后端悬空分组的 `key` 同一口径（`ledger_id|symbol`，symbol 原样不归一） */
export function discrepancyKey(row: {
  ledger_id: number | null;
  symbol: string | null;
}): string {
  return `${row.ledger_id ?? ""}|${row.symbol ?? ""}`;
}

/** 域 F 分组覆盖的业务键集合（含「挂错标的」组：那类流水同样由修正数据处置） */
export function rebuildCoveredKeys(
  dangling: DanglingRefList | null
): Set<string> {
  const groups = dangling?.groups;
  if (!Array.isArray(groups)) return new Set<string>();
  return new Set(groups.map(discrepancyKey));
}

/**
 * 这条差异是否只能去修正数据处置。
 *
 * 只看 `orphan`：`quantity` / `cost` 的修法本来就在核对差异里（补录 / 改数量），
 * 它们即便碰巧与某个悬空组同键（例如同标的另一批流水悬空），那条差异本身仍可裁决。
 */
export function isRebuildOnlyDiscrepancy(
  row: DiscrepancyItem,
  covered: Set<string>
): boolean {
  return row.discrepancy_type === "orphan" && covered.has(discrepancyKey(row));
}

/** 批量剔除：列表、计数、队列三处共用同一份判据，不各写一遍 `filter` */
export function withoutRebuildOnly(
  rows: DiscrepancyItem[],
  dangling: DanglingRefList | null
): DiscrepancyItem[] {
  const covered = rebuildCoveredKeys(dangling);
  if (covered.size === 0) return rows;
  return rows.filter(row => !isRebuildOnlyDiscrepancy(row, covered));
}
