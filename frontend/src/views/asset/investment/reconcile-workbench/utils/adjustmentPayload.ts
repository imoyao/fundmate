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

import type { AdjustmentPayload, DiscrepancyItem } from "@/api/reconciliation";

/** 三种裁决形态（与后端 `apply_decision` 的 kind 对齐） */
export type SupplementKind = "increment" | "set" | "anchor";

/** 弹窗表单的可提交快照（不含 UI 状态） */
export interface SupplementFormValue {
  kind: SupplementKind;
  op_type: string;
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
      explain:
        "把账上现在的份额与成本固定为核对基准：之后只核对这一天以后的新流水，之前的流水不再参与推导，这条差异随之消失。份额和成本直接取当前持仓，不用你填。",
      submit: "以此为准"
    };
  }
  if (kind === "set") {
    return {
      action: "补录这笔",
      explain:
        "把账上的份额和成本直接改成你填的数。适合券商账单显示的就是当前持仓、只是我们这边记错了的情况。",
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
