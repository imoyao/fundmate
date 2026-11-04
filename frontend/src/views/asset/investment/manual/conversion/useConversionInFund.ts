// frontend/src/views/asset/investment/manual/conversion/useConversionInFund.ts
// 转入基金的搜索与「当前持有」快选（#980 拆分自 ConversionForm.vue）。
//
// 与买入表单同一搜索源（`searchFunds`），不另造第二套搜索框。
// 两处过滤是业务规则，不是界面口味：
// - 搜索结果滤掉货基（后端亦拦截，前端先滤避免白跑一次试算）；
// - 快选列表排除转出基金本身（同基金转换无意义，`inLegValid` 也据此拦截）。

import { computed, ref, type ComputedRef } from "vue";
import { ElMessage } from "element-plus";
import { searchFunds, type FundSearchItem } from "@/api/funds";
import type { Position } from "@/api/types";
import type { ConversionFormModel } from "./conversionFormModel";

export function useConversionInFund(options: {
  form: ConversionFormModel;
  accountPositions: ComputedRef<Position[]>;
  selectedPosition: ComputedRef<Position | null>;
}) {
  const { form, accountPositions, selectedPosition } = options;

  const searchLoading = ref(false);
  const inFundOptions = ref<FundSearchItem[]>([]);

  async function remoteSearchFunds(query: string) {
    if (!query) {
      inFundOptions.value = [];
      return;
    }
    searchLoading.value = true;
    try {
      const res = await searchFunds(query);
      const arr = Array.isArray(res) ? res : (res?.data ?? []);
      inFundOptions.value = arr.filter(
        (f: FundSearchItem) => f.is_money_fund !== true
      );
    } catch {
      inFundOptions.value = [];
      ElMessage.warning("搜索服务暂不可用，请稍后重试");
    } finally {
      searchLoading.value = false;
    }
  }

  /** 第 1 步「当前持有」快选：排除转出基金本身 */
  const inFundCandidates = computed(() =>
    accountPositions.value.filter(
      p => p.symbol !== selectedPosition.value?.symbol
    )
  );

  /**
   * 已选转入基金的「标签兜底」。
   *
   * 快选按钮把 `form.inSymbol` 直接写成持仓代码，而它不在 `inFundOptions`（搜索结果）里，
   * el-select 找不到同名选项就把值原样显示成「002340」。这里只造一个**纯标签**选项
   * 把它接住——不伪造 `FundSearchItem` 的 type / subscription_rate，避免编数据。
   */
  const pickedInOption = computed(() => {
    const code = form.inSymbol;
    if (!code) return null;
    return { value: code, label: `${form.inName || code}（${code}）` };
  });

  function pickInFund(symbol: string, name: string) {
    form.inSymbol = symbol;
    form.inName = name;
  }

  function onInFundChange(code: string) {
    const hit = inFundOptions.value.find(f => f.code === code);
    form.inName = hit?.name ?? code;
  }

  return {
    searchLoading,
    inFundOptions,
    remoteSearchFunds,
    inFundCandidates,
    pickedInOption,
    pickInFund,
    onInFundChange
  };
}
