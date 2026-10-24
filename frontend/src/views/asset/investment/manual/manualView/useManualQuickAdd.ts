import { ref } from "vue";
import { ElMessage } from "element-plus";

import { createLedger } from "@/api/ledger";
import { LEDGER_TYPE_OPTIONS } from "@/constants";

import { quickAddFeeConfig } from "./manualEntryModel";

/**
 * 账户栏「新建账户」的极简通道（#980 拆分）。
 *
 * 与完整建账表单（`CreateAccountDialog`）的分工：这里只收**名称 + 渠道分组**两项，
 * 提交时必须下发 `channel_category`——后端据它派生 `ledger_type`（#1101）。
 * 历史上这里把分组值塞进 `ledger_type`，派生链落到
 * `map_ledger_type_to_channel_category('fund_platform')`，建出来的账户渠道分组为空、
 * 账本类型也错。这个坑由 `quickAddFeeConfig` 与下面的 payload 一起钉住。
 *
 * 状态（是否展开、输入到一半的名称）属于账户栏，不属于页面，
 * 所以整个收进这个 composable，由 `ManualAccountBar` 自己持有。
 */
export function useManualQuickAdd(onCreated: (id: number) => void) {
  const showQuickAdd = ref(false);
  const newAccountName = ref("");
  const newAccountType = ref("");
  const creatingAccount = ref(false);

  /** 「其他」不参与派生 ledger_type，极简通道不提供 */
  const quickAddTypeOptions = LEDGER_TYPE_OPTIONS.filter(
    opt => opt.value !== "other"
  );

  function resetQuickAdd() {
    showQuickAdd.value = false;
    newAccountName.value = "";
    newAccountType.value = "";
  }

  async function quickCreateAccount(reload: () => Promise<void> | void) {
    const name = newAccountName.value.trim();
    const channel = newAccountType.value;
    if (!name || !channel) return;

    creatingAccount.value = true;
    try {
      const payload: {
        name: string;
        channel_category: string;
        fee_config?: Record<string, unknown>;
      } = { name, channel_category: channel };

      const feeConfig = quickAddFeeConfig(channel);
      if (feeConfig) payload.fee_config = feeConfig;

      const res = await createLedger(payload);
      const newLedger = (res as any)?.data ?? res;
      await reload();
      if (newLedger?.id) {
        resetQuickAdd();
        onCreated(newLedger.id);
        ElMessage.success(`已创建账户「${newLedger.name || name}」并自动选中`);
      }
    } catch (e: any) {
      ElMessage.error(
        e?.response?.data?.message || e?.message || "创建账户失败"
      );
    } finally {
      creatingAccount.value = false;
    }
  }

  return {
    showQuickAdd,
    newAccountName,
    newAccountType,
    creatingAccount,
    quickAddTypeOptions,
    resetQuickAdd,
    quickCreateAccount
  };
}
