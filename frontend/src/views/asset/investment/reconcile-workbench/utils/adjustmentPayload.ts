/**
 * 裁决请求体 / 文案的构造（纯函数，可单测）。
 *
 * ## 为什么从弹窗里搬出来
 *
 * 这三件事原本散在 `SupplementDialog.vue` 的 computed 与 submit 里，而它们都是
 * **会静默写错库**的判断：
 * - `anchor` 若带上 `quantity`/`avg_price`，前端就成了「猜一个数字」的来源
 *   （差异行只有份额、没有成本价），写错就是把持仓改错；
 * - `increment` 的 `trade_date`/`confirm_date` 漏传，流水按确认日排序、列表里
 *   看起来像「日期错了」；
 * - 手续费不按 `op_type` 收口，会给银证转账记上一笔佣金。
 *
 * 放在 `.vue` 里只能靠人肉走查，放到这里就能被 `vitest` 咬住。
 */

import type {
  AdjustmentPayload,
  AdjustmentResult,
  DiscrepancyItem
} from "@/api/reconciliation";
import { reconQuantity } from "./reconDisplay";

/** 三种裁决形态（与后端 `apply_decision` 的 kind 对齐） */
export type SupplementKind = "increment" | "set" | "anchor";

/** 弹窗表单的可提交快照（不含 UI 状态） */
export interface SupplementFormValue {
  kind: SupplementKind;
  op_type: string;
  /**
   * 买入金额（元）：**只用于反算份额**，不单独提交。
   *
   * 2026-11-15 与记一笔对齐：基金买入时用户手里有金额与日期，份额是要算出来的那个数
   * （口径见 `@/utils/tradeAmountMath`，与 `useSharesLinkage` 共用）。提交给
   * `/reconciliation/adjustments/` 的仍是 `quantity` + `avg_price`——后端只认份额与
   * 成交价，多传一个金额就是多一个可以被改错的数。
   */
  buy_amount?: number;
  quantity?: number;
  avg_price?: number;
  fee?: number;
  confirm_date: string;
  snapshot_date: string;
  reason: string;
}

/**
 * 构造裁决请求体。
 *
 * `today` 由调用方传入（本地日历日），不在这里取 `new Date()`——纯函数才能被测试
 * 固定住「快照日缺省值」这个行为，也避免 UTC 把上海时间的凌晨算成前一天。
 */
export function buildAdjustmentPayload(
  row: DiscrepancyItem,
  form: SupplementFormValue,
  today: string
): AdjustmentPayload {
  // anchor 只传差异 id：份额与成本由后端从持仓读取。差异行只有份额、没有成本价，
  // 前端硬填只能靠猜；多一个数字来源就多一个把持仓写错的机会。
  if (form.kind === "anchor") {
    return {
      kind: "anchor",
      discrepancy_id: row.id,
      reason: form.reason || undefined
    };
  }

  const payload: AdjustmentPayload = {
    kind: form.kind,
    discrepancy_id: row.id,
    symbol: row.symbol,
    name: row.display_name || undefined,
    ledger_id: row.ledger_id,
    quantity: form.quantity,
    avg_price: form.avg_price,
    reason: form.reason || undefined
  };

  if (form.kind === "increment") {
    payload.op_type = form.op_type;
    // 用户填的是成交当天：trade_date 与 confirm_date 同值。后端 `resolve_trade_date`
    // 缺省回落 confirm_date，显式补上 trade_date 才能让流水按真实成交日排序。
    payload.trade_date = form.confirm_date || undefined;
    payload.confirm_date = form.confirm_date || undefined;
    // 手续费只有买卖有。存入/取出是银证转账，用户切过来时旧值还在，故按 op_type 收口。
    const hasTradeFee = form.op_type === "buy" || form.op_type === "sell";
    payload.fee =
      hasTradeFee && typeof form.fee === "number" ? form.fee : undefined;
  } else {
    payload.snapshot_date = form.snapshot_date || today;
  }
  return payload;
}

/** 提交后的提示文案（「没轧平」必须说清还能接着补，不能报成已完成） */
export function adjustmentSuccessMessage(
  kind: SupplementKind,
  stillPending: boolean
): string {
  if (stillPending) {
    return kind === "anchor"
      ? "已写入基准，这条差异还没消失，刷新后请再确认"
      : "这笔已补上，账还没平，可以在队列里继续补";
  }
  if (kind === "anchor") return "已以此为准";
  return kind === "set" ? "持仓已改" : "这笔已补上";
}

/**
 * 「按流水重算份额」的请求体（#3134）。
 *
 * 只传差异编号 + 标的：份额、成本一律由后端按持仓名下流水派生，前端多传一个数字就是
 * 多一个把持仓写错的机会（与 `anchor` 同一约定）。`symbol` / `ledger_id` 只用于报错时
 * 指认对象——后端以差异行为准。
 */
export function buildRecomputePayload(row: DiscrepancyItem): AdjustmentPayload {
  return {
    kind: "recompute",
    discrepancy_id: row.id,
    symbol: row.symbol,
    ledger_id: row.ledger_id
  };
}

/**
 * 重算后的结果文案。
 *
 * 三种结局都必须说清，因为它们的下一步完全相反：
 * - 行被删了（流水一条都没有）—— 持仓没了，得回去补流水重建；
 * - 差额平了 —— 收工；
 * - 差额还在 —— 说明流水本身与账单不符，别在这里反复点，去对照投资轨迹。
 */
export function recomputeResultMessage(
  result: AdjustmentResult | undefined
): string {
  const done = result?.recompute;
  if (!done) return "已按流水重算份额";
  if (done.deleted) {
    return `这条持仓没有任何流水支撑，已删除（原 ${reconQuantity(done.quantity_before)}）。要用它请在记完流水后重新建仓`;
  }
  const after = reconQuantity(done.quantity_after);
  if (result?.discrepancy?.status === "cleared") {
    return `已按流水改成 ${after}，这条差异已平`;
  }
  return `已按流水改成 ${after}，但差额仍在：对照「投资轨迹」看看是不是流水本身没记全`;
}

/** 弹窗里与模式相关的三段文案 */
export interface SupplementLabels {
  /** 动作短名（弹窗标题与按钮共用，避免「标题说补录、按钮写基准」） */
  action: string;
  explain: string;
  submit: string;
}

/** 按模式产出文案：一处定义，标题/说明/按钮不会各说各的 */
export function supplementLabels(kind: SupplementKind): SupplementLabels {
  if (kind === "anchor") {
    return {
      action: "以此为准",
      // #3127：初版文案只说「缺基准、不用管」，但账上份额未必可信。必须同时给出
      // 「怀疑份额本身错」的退出路径，否则一键固化后 manual 锚点还会挡住快照覆盖。
      explain:
        "把账上现在的份额与成本固定为核对基准：之后只核对这一天以后的新流水，之前的流水不再参与推导，这条差异随之消失。份额和成本直接取当前持仓，不用你填。请确认账上份额与券商账单一致；如果怀疑份额本身记错了（比如已经卖完却还挂着），请关掉这里，先到「交易记录」核对流水，再按账单改份额。",
      submit: "以此为准"
    };
  }
  if (kind === "set") {
    return {
      action: "改成账单份额",
      explain:
        "把账上的份额和成本直接改成你填的数。适合券商账单显示的就是当前持仓、只是我们这边记错了的情况；账单上已经没有这只了，份额填 0 即按账单清仓（系统不会按流水替你清仓）。",
      submit: "改成这个持仓"
    };
  }
  return {
    action: "补录这笔",
    explain:
      "补上缺的那笔买卖，会同时记一条交易流水并重算持仓。适合少记了一笔买入或卖出的情况。",
    submit: "补上这笔"
  };
}
