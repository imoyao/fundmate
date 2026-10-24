import { computed, ref, type Ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { estimateRedeemFee, syncFundFees } from "@/api/funds";

interface SellFeeForm {
  type: string;
  trade_date: string;
  quantity: number | undefined;
  fee: number | undefined;
}

/**
 * 卖出（赎回）费用与费率分布（#980 从 SellForm 拆出）。
 *
 * 口径：按持仓买入确认日起算的持有天数，用后端 estimateRedeemFee 拿「全仓分布 +
 * 本次份额分布 + 合计费用」，FIFO 扣减由后端算。用户手改过费用后（feeManuallyChanged）
 * 不再覆盖；缺费率规则时给「立即更新」入口（syncFundFees 拉一次再算）。
 */
export function useSellFee(deps: {
  form: SellFeeForm;
  selectedPosition: Ref<any>;
}) {
  const { form, selectedPosition } = deps;

  const feeError = ref("");
  const feeRateDialogVisible = ref(false);
  // 保留用于兼容，但主要使用 holdFeeDetails
  const feeRateTableData = ref<any[]>([]);
  /** 全仓持有分布 */
  const holdFeeDetails = ref<any[]>([]);
  /** 指定份额分布 */
  const sellFeeData = ref<any[]>([]);
  const feeManuallyChanged = ref(false);

  /** 计算实际可用于费率计算的买入总份额 */
  const totalCalculatedHold = computed(() =>
    holdFeeDetails.value.reduce((sum, item) => sum + item.shares, 0)
  );

  /** 当前输入的份额（>0 时有效） */
  const enteredShares = computed(() => {
    const q = form.quantity;
    return q !== undefined && q !== null && q > 0 ? q : 0;
  });

  /** 合并全仓和指定份额数据，用于弹窗表格 */
  const mergedFeeData = computed(() => {
    const holdData = holdFeeDetails.value;
    const sellData = sellFeeData.value;
    if (holdData.length === 0) return [];
    const sellMap: Record<number, number> = {};
    sellData.forEach((item: any) => {
      sellMap[item.rate] = (sellMap[item.rate] || 0) + item.shares;
    });
    return holdData.map((h: any) => ({
      range: h.range,
      rate: h.rate,
      holdShares: h.shares,
      sellShares: sellMap[h.rate] ?? 0
    }));
  });

  const fetchFundFeeRules = async (
    positionId: number,
    tradeDate: string,
    shares?: number
  ) => {
    const payload: any = {
      position_id: positionId,
      sell_date: tradeDate
    };
    if (shares !== undefined && shares !== null && shares > 0) {
      payload.shares = shares;
    }
    const res: any = await estimateRedeemFee(payload);
    const data = res.data;
    return {
      total_fee: data?.total_fee || 0,
      holdings: (data?.holdings || []).map((r: any) => ({
        range: r.range,
        shares: r.shares,
        rate: r.rate
      })),
      sell: (data?.sell || []).map((r: any) => ({
        range: r.range,
        shares: r.shares,
        rate: r.rate
      }))
    };
  };

  function clearFeeState() {
    holdFeeDetails.value = [];
    sellFeeData.value = [];
    feeError.value = "";
  }

  const calculateFeeAndRate = async () => {
    if (!selectedPosition.value || form.type !== "fund" || !form.trade_date) {
      form.fee = 0;
      clearFeeState();
      return;
    }
    const buyDate = selectedPosition.value.confirm_date;
    if (!buyDate) {
      clearFeeState();
      return;
    }

    try {
      const { total_fee, holdings, sell } = await fetchFundFeeRules(
        selectedPosition.value.id,
        form.trade_date,
        form.quantity || 0
      );
      if (!feeManuallyChanged.value) {
        form.fee = total_fee;
      }
      holdFeeDetails.value = holdings;
      sellFeeData.value = sell.length > 0 ? sell : [];
      feeRateTableData.value = holdings;
      feeError.value = "";
    } catch (e: any) {
      // 从 Axios 错误中提取后端返回的 message
      let msg = "暂时无法获取费率分布";
      if (e?.response?.data?.message) {
        msg = e.response.data.message; // 后端返回的业务错误消息
      } else if (e?.message) {
        msg = e.message;
      }
      console.warn("费率查询失败", msg, e);
      holdFeeDetails.value = [];
      sellFeeData.value = [];
      feeError.value = msg;
    }
  };

  function onFeeManualChange() {
    feeManuallyChanged.value = true;
  }

  /** 选完持仓/换日期后重置手改标记与分布（原 onPositionSelect 里的复位动作） */
  function resetFeeState() {
    feeManuallyChanged.value = false;
    feeRateDialogVisible.value = false;
    clearFeeState();
  }

  /** 只复位「用户手改过费用」标记：换持仓后允许重新按规则算（分布留给下一次请求覆盖） */
  function resetFeeManualFlag() {
    feeManuallyChanged.value = false;
  }

  const openFeeRateDialog = async () => {
    if (!selectedPosition.value) {
      ElMessage.info("请先选择持仓");
      return;
    }
    if (!selectedPosition.value.confirm_date) {
      ElMessage.warning(
        "该持仓缺少买入确认日期，无法查询费率。请先在持仓详情中补充确认日期。"
      );
      return;
    }
    await calculateFeeAndRate();

    if (holdFeeDetails.value.length === 0) {
      if (feeError.value.includes("暂无赎回费率规则")) {
        // 自定义弹窗：提供"更新费率"按钮
        ElMessageBox.confirm(
          "该基金尚未收录费率信息，是否立即更新？",
          "费率数据缺失",
          {
            confirmButtonText: "立即更新",
            cancelButtonText: "我知道了",
            type: "warning",
            beforeClose: async (action, instance, done) => {
              if (action === "confirm") {
                instance.confirmButtonLoading = true;
                try {
                  await syncFundFees(selectedPosition.value.symbol);
                  ElMessage.success("费率更新成功");
                  // 重新计算费率（此时应该能获取到数据）
                  await calculateFeeAndRate();
                  if (holdFeeDetails.value.length > 0) {
                    // 打开费率分布弹窗
                    feeRateDialogVisible.value = true;
                  } else {
                    ElMessage.info("费率已更新但仍无法计算，请手动输入费用");
                  }
                } catch {
                  ElMessage.error("更新失败，请稍后重试或手动输入费用");
                } finally {
                  instance.confirmButtonLoading = false;
                  done();
                }
              } else {
                done();
              }
            }
          }
        );
      } else {
        ElMessage.error(feeError.value || "暂时无法获取费率分布");
      }
      return;
    }
    // 正常打开费率分布
    feeRateDialogVisible.value = true;
  };

  return {
    feeError,
    feeRateDialogVisible,
    feeRateTableData,
    holdFeeDetails,
    sellFeeData,
    feeManuallyChanged,
    totalCalculatedHold,
    enteredShares,
    mergedFeeData,
    calculateFeeAndRate,
    onFeeManualChange,
    openFeeRateDialog,
    resetFeeState,
    resetFeeManualFlag
  };
}
