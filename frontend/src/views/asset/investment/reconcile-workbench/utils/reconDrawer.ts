/**
 * 对账抽屉（`components/ReconQueueDetail.vue` / `ReconInvestmentTrail.vue`）
 * 的三条纯判据，2026-11-12 从组件里下沉：组件要守 `check_vue_size.mjs` 的
 * 400 行门禁，判据本体离开 Vue 上下文才能被 vitest 直接覆盖。
 */
import type { ReconQueuePayload } from "./reconQueue";

/** 抽屉头部要的「产品标识」：payload 里能取到的 symbol + 名称 */
export interface ReconAssetRef {
  symbol: string;
  name: string | null;
}

/**
 * 抽屉头部的产品标识来源。产品名 + 代码在**同一屏内只说一次**（owner 截图
 * 指出头部与「来龙去脉」卡各说一遍是在侵占决策空间）：头部用
 * `reconAssetHeading`，卡片不再复述。
 *
 * 域 G / import 这类待办指认的是**账本或入口**而不是产品（orphan 的标题就是
 * 账本名），返回 null 让头部退回队列项原标题——此时不存在「产品名说两遍」。
 */
export function reconItemAsset(
  payload: ReconQueuePayload
): ReconAssetRef | null {
  switch (payload.kind) {
    case "discrepancy":
    case "dangling":
      return {
        symbol: payload.row.symbol,
        name: payload.row.display_name ?? null
      };
    case "tax":
      return { symbol: payload.row.symbol, name: payload.row.name || null };
    case "ghost":
      return {
        symbol: payload.row.symbol,
        name: payload.row.display_name ?? null
      };
    case "ghostIgnored":
      // 忽略快照的 symbol 可能为 null：给空串让头部退回 item.title
      return {
        symbol: payload.row.symbol ?? "",
        name: payload.row.display_name ?? null
      };
    case "eaccount":
      return { symbol: payload.row.symbol, name: payload.row.name || null };
    default:
      return null;
  }
}

/** 投资轨迹的取数键：只消费确实带 symbol 的原始对象；无产品（orphan/import）返回 null */
export function reconTrailQuery(
  payload: ReconQueuePayload
): { symbol: string; ledgerId: number | null } | null {
  switch (payload.kind) {
    case "discrepancy":
      return { symbol: payload.row.symbol, ledgerId: payload.row.ledger_id };
    case "tax":
    case "eaccount":
    case "ghost":
      return { symbol: payload.row.symbol, ledgerId: null };
    case "dangling":
      return { symbol: payload.row.symbol, ledgerId: payload.row.ledger_id };
    default:
      return null;
  }
}

/**
 * 「投资轨迹」里哪一行能编辑（纯函数，vitest 用例见 `__tests__/reconDrawer.spec.ts`）。
 *
 * 后端 `PATCH /api/ledgers/<ledger_id>/transactions/<id>/` 只接受已归属账本的
 * 流水（`backend/app/domains/ledgers/views.py`），编辑表单也以 `t.ledger_id`
 * 为前提；`DELETE /api/transactions/<id>/` 只按 family_id 鉴权，删除不受限。
 *
 * 返回空串 = 可编辑；非空 = 置灰原因（同一句给行内 tooltip，说清为什么不能点）。
 */
export function trailEditBlockReason(row: {
  ledger_id?: number | null;
}): string {
  if (row.ledger_id == null) {
    return "这笔流水还没归属账本，归属后才能编辑";
  }
  return "";
}
