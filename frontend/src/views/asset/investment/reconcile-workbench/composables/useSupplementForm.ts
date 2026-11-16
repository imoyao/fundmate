import { computed, reactive, ref } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import type { DiscrepancyItem } from "@/api/reconciliation";
import type { SupplementFormValue } from "../utils/adjustmentPayload";
import { defaultSupplementKind } from "../utils/discAction";
import { inferSupplementOpType } from "../utils/reconSupplement";

/**
 * 补录表单的模型 / 校验 / 重置（2026-11-15 从 `SupplementDialog.vue` 拆出）。
 *
 * 拆出的直接原因：弹窗要加「买入金额」（基金按金额自动算份额，与记一笔同口径），
 * 而 `SupplementDialog.vue` 已顶在页面规模门禁的 400 行上限（issue #980），
 * 再往里塞字段会当场判红。按项目纪律拆逻辑（不是拆模板、更不是改基线）。
 *
 * 顺带的好处：「打开弹窗时的默认值」——预填方向（`inferSupplementOpType`）与默认
 * 模式（`defaultSupplementKind`）都是会静默写错库的判断（方向反了就是一笔反向交易），
 * 集中在这里才有地方给它们补单测。
 */
export function useSupplementForm(getTarget: () => DiscrepancyItem | null) {
  const formRef = ref<FormInstance>();

  const form = reactive<SupplementFormValue>({
    kind: "increment",
    op_type: "buy",
    buy_amount: undefined,
    quantity: undefined,
    avg_price: undefined,
    fee: undefined,
    confirm_date: "",
    snapshot_date: "",
    reason: ""
  });

  const rules = computed<FormRules>(() => ({
    quantity: [
      {
        validator: (_rule, value, callback) => {
          if (typeof value !== "number" || !Number.isFinite(value)) {
            callback(new Error("份额还没填"));
            return;
          }
          if (value <= 0) {
            callback(new Error("份额要大于 0"));
            return;
          }
          callback();
        },
        trigger: "change"
      }
    ],
    avg_price: [
      {
        validator: (_rule, value, callback) => {
          if (typeof value !== "number" || !Number.isFinite(value)) {
            callback(new Error("单价还没填"));
            return;
          }
          if (value <= 0) {
            callback(new Error("单价要大于 0"));
            return;
          }
          callback();
        },
        trigger: "change"
      }
    ]
  }));

  /**
   * 每次打开重置表单。只预填方向，不预填数量/金额（数量口径待 owner 拍板，
   * 不自作主张）；`no_anchor` 差异没有「补一笔」的选项——补的金额是编出来的，
   * 只会把「缺基准」写歪，故由 `defaultSupplementKind` 决定默认模式。
   */
  function resetForm(today: string): void {
    form.kind = defaultSupplementKind(getTarget());
    // 按当前差异重新算方向（不是写死 buy）：打开弹窗 / 关闭后重开都要走这里
    form.op_type = inferSupplementOpType(getTarget()) ?? "buy";
    form.buy_amount = undefined;
    form.quantity = undefined;
    form.avg_price = undefined;
    form.fee = undefined;
    form.confirm_date = "";
    form.snapshot_date = today;
    form.reason = "";
    formRef.value?.clearValidate();
  }

  /** 切模式 / 切交易类型时清掉上一档的红字 */
  function clearValidate(): void {
    formRef.value?.clearValidate();
  }

  return { form, formRef, rules, resetForm, clearValidate };
}
