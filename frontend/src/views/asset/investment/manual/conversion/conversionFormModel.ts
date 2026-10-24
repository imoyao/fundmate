// frontend/src/views/asset/investment/manual/conversion/conversionFormModel.ts
// 转换表单的模型 / 默认值 / 选项表（#980 拆分自 ConversionForm.vue）。
//
// 为什么单独成文件：`ConversionForm.vue` 原来 1702 行，单一文件里同时住着
// 三步向导的模板、试算与提交两套编排、561 行样式。「默认值」是三处都要引用的
// 契约（`resetForm`、模板初值、单测），放在 SFC 里就只能靠读整份文件才能确认，
// 所以先把它钉成一份可测的字面量。

/**
 * 转入口径：金额 / 份额二选一。
 *
 * 后端 `in_amount` / `in_quantity` 互斥（同时传直接拒绝），所以前端只能持一个
 * 口径标记，另一个口径的值留在 `form.inAmount` / `form.inQuantity` 里不发送。
 */
export type InMode = "amount" | "quantity";

/** 差额去向：空串 = 用户还没选（有差额时 `submitValid` 会因此为 false） */
export type RefundMode = "" | "money_fund" | "account_cash";

export interface ConversionFormModel {
  /** 转出持仓 ID（同时也是「转出基金」的选择值） */
  positionId: number | null;
  /** 转出份额；`undefined` = 未填 */
  quantity: number | undefined;
  /** 交易日 YYYY-MM-DD */
  trade_date: string;
  /** 是否 15:00 后提交（按下一交易日净值） */
  isAfter15: boolean;
  /** 转入基金代码（6 位裸码） */
  inSymbol: string;
  /** 转入基金名称（选中的展示名；快选路径下没有搜索结果可查） */
  inName: string;
  /** 指定转入金额（元） */
  inAmount: number | undefined;
  /** 当前生效的转入口径 */
  inMode: InMode;
  /** 指定转入份额（份） */
  inQuantity: number | undefined;
  /** 差额去向 */
  refundMode: RefundMode;
}

/**
 * 转入口径（2 档「多选一」）。
 *
 * 模板里内嵌在输入框右端做文字开关，用 `as const` 保住字面量类型，
 * `aria-pressed` / `form.inMode` 比较才不会退化成 string。
 */
export const IN_MODE_OPTIONS = [
  { label: "按金额", value: "amount" },
  { label: "按份额", value: "quantity" }
] as const;

/**
 * 表单默认值。
 *
 * `trade_date` 走 `toISOString()`（UTC）：这是原实现的行为，本次拆分**不改**——
 * 东八区 00:00–08:00 之间它会给出「昨天」，属独立问题，改动会牵动试算参数，
 * 不在「零行为变更」范围内。
 */
export const defaultConversionForm = (): ConversionFormModel => ({
  positionId: null,
  quantity: undefined,
  trade_date: new Date().toISOString().slice(0, 10),
  isAfter15: false,
  inSymbol: "",
  inName: "",
  inAmount: undefined,
  inMode: "amount",
  inQuantity: undefined,
  refundMode: ""
});
