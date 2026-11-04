import { nextTick, type ComputedRef, type Ref } from "vue";
import type { FormInstance } from "element-plus";
import { defaultSellForm, type SellFormModel } from "../sellFormModel";

/**
 * 卖出表单的「账户切换 / 选持仓」动作（#980 从 SellForm 拆出）。
 *
 * 两件事都靠清空 + 重建下拉来保证不串数据：切账户保留 ledger_id、清掉持仓与标的；
 * 选持仓回填标的四件套（symbol/name/market/type）、价格默认取现价（无则成本价），
 * 份额与费用清零后重算费率。
 */
export function useSellFormActions(deps: {
  form: SellFormModel;
  formRef: Ref<FormInstance | undefined>;
  selectedPosition: Ref<any>;
  /** 当前账户下的持仓（选持仓时按 id 回查） */
  accountPositions: ComputedRef<any[]>;
  qtyTouched: Ref<boolean>;
  showPositionSelect: Ref<boolean>;
  positionSelectKey: Ref<number>;
  resetTradeDate: () => void;
  /** 清账户时把「用户手改标记 + 分布 + 弹窗显隐」一起复位 */
  resetFeeState: () => void;
  /** 只复位「用户手改过费用」标记，允许按规则重算 */
  resetFeeManualFlag: () => void;
  calculateFeeAndRate: () => void;
}) {
  const { form, selectedPosition, qtyTouched, showPositionSelect } = deps;

  function clearFormData() {
    qtyTouched.value = false;
    showPositionSelect.value = false;
    nextTick(() => {
      const currentLedgerId = form.ledger_id;
      const defaults = defaultSellForm();
      Object.keys(defaults).forEach(key => {
        (form as any)[key] = (defaults as any)[key];
      });
      form.ledger_id = currentLedgerId;
      form.positionId = null;

      selectedPosition.value = null;
      deps.resetFeeState();
      deps.resetTradeDate();

      deps.positionSelectKey.value++;
      deps.formRef.value?.clearValidate();
      showPositionSelect.value = true;
    });
  }

  function onAccountChange() {
    // 直接调用 clearFormData，它内部会保存并恢复 ledger_id
    clearFormData();
  }

  function onPositionSelect(positionId: number) {
    const pos = deps.accountPositions.value.find(
      (p: any) => p.id === positionId
    );
    if (!pos) return;
    selectedPosition.value = pos;
    form.symbol = pos.symbol;
    form.name = pos.name;
    form.market = pos.market;
    form.type = pos.type;
    form.currency = pos.currency;
    form.price = pos.current_price ?? pos.avg_price;
    form.quantity = undefined;
    qtyTouched.value = false;
    form.fee = 0;
    deps.resetFeeManualFlag();
    deps.resetTradeDate();
    deps.calculateFeeAndRate();
    // 股票价格区间由 useSecurityPriceRange 随持仓/交易日自动刷新（#948 统一约束）
  }

  return { clearFormData, onAccountChange, onPositionSelect };
}
