/**
 * 导入预览的「金额 ÷ 份额 补单价」（#2903）。
 *
 * ## 为什么单独成一个文件
 *
 * 同一条规则此前在 `useImportWizard.ts` 里**写了两份**：OCR 通道一份（无守卫）、
 * 文件通道一份（4 条件守卫），计算式逐字相同、守卫却不同。两处各写一份必然漂移，
 * 本卡就是漂移的实例。判定与计算收敛到这里，调用点各留一行。
 *
 * ## 为什么不能照抄文件通道那 4 个条件
 *
 * 旧文件通道守卫是 `!isRowBlocked(row) && !row.is_cash_transfer && !row.error &&
 * !row.is_duplicate`。`isRowBlocked` 在 `price <= 0` 时返回 **true**（见
 * `previewPredicates.isRowBlocked`），而补价的前提**正是**「单价缺失」——两者互斥。
 * 于是那 4 个条件实际只放行 `isRowBlocked` 的豁免类型（`tax` / `dividend` /
 * `bond_redeem` / `split` / `money_fund` / `reverse_repo` / `consumed_by`），
 * 却把守卫想服务的普通成交行（buy / sell 缺价）全部拒之门外。
 * **条件写反了**：该补的一个没补，不该补的全补了。
 *
 * ## 原样保留 OCR 的「无守卫」也不行
 *
 * `tax` 的金额是税额、`bond_redeem` 的金额是兑付到账净额（面值 + 应计利息 − 代扣费），
 * 二者都不是「这份额对应的成交额」，相除得到的数不是单价。补了轻则误导，重则让
 * 「金额 / 单价 / 数量」三者看起来自洽、掩盖真实差异。
 *
 * 回归网 `__tests__/smartFillPrice.spec.ts` 同时钉住三件事：新口径逐类放行/拒绝、
 * 旧守卫对普通缺价行恒 false（「条件写反」的机器证据）、以及两处调用点共用本模块。
 *
 * ## #2902 定案口径（2026-11-05，owner 拍板）
 *
 * 装载期补价**算**「自动填充」：补价必须同时写 `_autoFilled: ["price"]`。
 * 否则 `pickFilledRows` / `filledFieldsLabel` 只认 `_autoFilled`，用户既看不到单价被改写的行，
 * `BatchFixDialogs` 里那句「点顶部【撤销上一步】可回滚」也无从兑现。
 *
 * 但「可回滚」**不塞进批量修正的撤销栈**，改为逐行【恢复原始值】，三条理由：
 * - 撤销栈撤的是用户上一次批量修正；装载期补价是解析期规范化，用户从未执行过这个动作。
 *   绑到任意一次撤销上，会把刚补好的行变回 `isRowBlocked` 不可导入，语义错乱。
 * - 撤销快照的 `before.price` 本来就是补过的值（快照拍在批量修复之前、补价之后），
 *   把 `smartFilled` 加进 `UNDO_FIELDS` 也退不回原始空值——字段清单不是根因，时机才是。
 * - 恢复所需信息存在**行对象**上（`_smartFillOrigin`），草稿持久化整行，
 *   `restoreDraft` 之后仍可恢复；撤销栈是组件内 ref，恢复草稿后会丢，做不到这一点。
 *
 * `smartFilled` 保留为兼容标记（`cellEditLogic.smartFill` 的行内编辑也写它），
 * 但**唯一消费口径是 `_autoFilled`**：清单、字段名标签、恢复判据都只读它。
 * 行内就地编辑（`finishEdit`）的补值不在本卡范围，另行治理。
 */

/**
 * 金额与「份额对应的成交额」无关、因而**不能**用 金额/份额 反推单价的类型。
 *
 * 与 `previewPredicates.QTY_PRICE_OPTIONAL_OPS` 的差集**恰好只有 `dividend_reinvest`**，
 * 这是有意的——两个集合回答的是两个问题：
 * - `QTY_PRICE_OPTIONAL_OPS`：入账**是否要求**价格齐全（缺了不拦）；
 * - 本集合：能否由金额**反推**价格。
 *
 * 红利再投属于「不要求价格，但金额÷份额就是净值」：后端
 * `position_service.process_dividend_reinvest` 正是这么反推的（见 `position_service.py`
 * 中「净价缺失时允许按 金额/份额 反推」）。前端若不补，预览显示「无价格」而入库却有
 * 价格，两边口径又分叉一次。
 *
 * `split`（拆分）本就没有金额，会先被金额判据挡掉，显式列出只为读起来完整。
 */
export const PRICE_NOT_DERIVABLE_OPS = new Set([
  "tax",
  "dividend",
  "dividend_cash",
  "split",
  "bond_redeem"
]);

/**
 * 这一行该不该用「金额 ÷ 份额」补单价。
 *
 * 依次排除：
 * 1. 解析错误 / 疑似重复 / 资金划转 / 被配对消费——要么不入账，要么数据本身不可信；
 *    补价会让脏行看起来可导入，还会连带改变勾选与问题卡片统计
 *    （`isRowBlocked` 对前三类同样放行，两处口径同源）；
 * 2. `PRICE_NOT_DERIVABLE_OPS`——金额语义不对，反推出来的不是单价；
 * 3. `money_fund` / `reverse_repo`——货币基金净值恒 1、逆回购的金额与「张数」不构成
 *    单价 × 数量关系（这两类在 `isRowBlocked` 里同样被豁免「不要求价格」）；
 * 4. 数值前提：份额 > 0、金额**为正**、单价缺失或非正。
 *
 * 金额为什么要 > 0：部分数据源把卖出记成负数，`金额 ÷ 份额` 会算出负单价；补一个负价
 * 比不补更糟（入库必然错，且预览里看不出这是「符号问题」）。宁可留在「需修正」让用户
 * 看见，也不要用一个看起来完整的错值盖住它。`autoFillMissing` 的 `amt <= 0` 排除同源。
 */
export function shouldSmartFillPrice(row: any): boolean {
  if (row.error || row.is_duplicate || row.is_cash_transfer) return false;
  if (row.consumed_by) return false;
  if (PRICE_NOT_DERIVABLE_OPS.has(row.op_type)) return false;
  if (row.type === "money_fund" || row.type === "reverse_repo") return false;
  const qty = parseFloat(row.quantity);
  const prc = parseFloat(row.price);
  const amt = parseFloat(row.amount);
  if (isNaN(qty) || qty <= 0) return false;
  if (!isNaN(prc) && prc > 0) return false;
  return !isNaN(amt) && amt > 0;
}

/**
 * 就地补价，返回是否真的补了（供调用点与测试断言）。
 *
 * 精度 4 位对齐既有口径（`cellEditLogic.smartFill` 同款 `toFixed(4)`）：净值本身就是
 * 4 位小数，多留位数只会把浮点尾巴带进「数量 × 单价 = 金额」的比对。
 *
 * #2902：除了改 price，还要留三样东西——`_autoFilled` 让行进「已填充数据」清单，
 * `smartFilled` 兼容旧标记，`_smartFillOrigin` 记下「改前 / 改后」供逐行恢复。
 * 先存 before 再写 price，顺序反了会把补过的值当成原始值。
 */
export function fillSmartPrice(row: any): boolean {
  if (!shouldSmartFillPrice(row)) return false;
  const filled = parseFloat(
    (parseFloat(row.amount) / parseFloat(row.quantity)).toFixed(4)
  );
  row._smartFillOrigin = { before: row.price, after: filled };
  row.price = filled;
  row.smartFilled = true;
  row._autoFilled = [...new Set([...(row._autoFilled || []), "price"])];
  return true;
}

/** 装载期补价的「改前 / 改后」原值，随行走草稿；after 同时是「用户没再动过」的判据 */
export interface SmartFillOrigin {
  before: unknown;
  after: number;
}

/**
 * 这一行现在能不能点【恢复原始值】。
 *
 * 必须是补价行，且 price 仍是当初补进去的那个值——用户随后在表格里手改过单价、
 * 或批量修正又动过 price，就不该再让一个「恢复」按钮把他的输入覆盖掉。
 */
export function canRestoreSmartFilledPrice(row: any): boolean {
  const origin = row._smartFillOrigin as SmartFillOrigin | undefined;
  return !!origin && row.price === origin.after;
}

/**
 * 把装载期补价整组退回：price 还原、清单标记移除、兼容标记与原始值一并清掉。
 * 返回是否真的恢复；只改行数据，不碰 Vue 状态——勾选与统计由调用方重算。
 */
export function restoreSmartFilledPrice(row: any): boolean {
  if (!canRestoreSmartFilledPrice(row)) return false;
  const origin = row._smartFillOrigin as SmartFillOrigin;
  row.price = origin.before;
  delete row._smartFillOrigin;
  delete row.smartFilled;
  const rest = (row._autoFilled || []).filter((f: string) => f !== "price");
  if (rest.length) row._autoFilled = rest;
  else delete row._autoFilled;
  return true;
}
