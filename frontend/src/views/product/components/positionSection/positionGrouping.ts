import type { Position } from "@/api/types";
import { sumUp } from "../productPositionMetrics";
import type { ChannelGroup } from "./positionTypes";

/**
 * 把持仓行按账户（`ledger_id`）聚合成组（#980 拆分时从父组件抽出）。
 *
 * 抽出来的唯一理由是**可测**：分组键、缺省账户名、未归档兜底这三条以前埋在
 * `<script setup>` 里，只能靠 e2e 间接覆盖。纯函数化后由
 * `__tests__/positionGrouping.spec.ts` 直接钉住。
 *
 * 顺序即渲染顺序：按 `ledger_id` **首次出现**的次序输出，不排序、不重排——
 * 后端已按建仓先后给出，前端再排序会让「账户出现的先后」与用户预期不符。
 */
export function groupByLedger(rows: Position[]): ChannelGroup[] {
  const map = new Map<number | null, Position[]>();
  for (const row of rows) {
    const ledgerId = row.ledger_id ?? null;
    const bucket = map.get(ledgerId);
    if (bucket) {
      bucket.push(row);
    } else {
      map.set(ledgerId, [row]);
    }
  }

  return Array.from(map.entries()).map(([ledgerId, groupRows]) => ({
    key: String(ledgerId ?? "ungrouped"),
    name:
      groupRows[0]?.account_name ||
      (ledgerId ? `账户 #${ledgerId}` : "未归档持仓"),
    ledgerId,
    rows: groupRows,
    ...sumUp(groupRows)
  }));
}

/**
 * `YYYY-MM-DD` → `MM-DD`（#2007）。
 *
 * 当日盈亏的基准日只在「当日」这个标签旁边做注脚，年份在这里是噪声——
 * 完整日期由列说明给出，指标标签上留太长的串会把版面挤歪。
 * 非 10 位（后端偶发给完整时间戳或空串）时原样返回，不做猜测式截断。
 */
export function shortDate(iso: string): string {
  return iso.length === 10 ? iso.slice(5) : iso;
}
