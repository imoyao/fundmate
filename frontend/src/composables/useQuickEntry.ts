import { ref, type Ref } from "vue";
import { getLedgers, type LedgerListItem } from "@/api/ledger";
import { emitter } from "@/utils/mitt";

/**
 * 快捷录入的三个表单组件（BuyForm / SellForm / DividendForm）对外暴露的通道。
 *
 * 它们都 `defineExpose({ handleSubmit, resetForm, isDirty })`；这里只声明父层用得到的
 * 两个。`isDirty` 由各自的宿主（TransactionDrawer / 手工录入页）从
 * `InstanceType<typeof XxxForm>` 读，不走这条通道，故不在此声明。
 */
export interface QuickEntryFormExposed {
  handleSubmit: () => Promise<void>;
  resetForm: () => void;
}

/** 提交通道只有这三个（其余操作类型走各自的分支） */
export type QuickEntrySubmitOpType = "buy" | "sell" | "dividend";

export function useQuickEntry(opts?: { autoLoad?: boolean }) {
  const ledgers = ref<LedgerListItem[]>([]);
  const loading = ref(false);

  async function loadLedgers() {
    loading.value = true;
    try {
      const res = await getLedgers();
      // 后端信封 { data, message }，http 拦截器已剥到 body，故这里取一层 data
      ledgers.value = res.data ?? [];
    } catch {
      ledgers.value = [];
    } finally {
      loading.value = false;
    }
  }

  if (opts?.autoLoad) loadLedgers();

  return { ledgers, loading, loadLedgers };
}

export function useQuickEntrySubmit(
  opType: Ref<QuickEntrySubmitOpType>,
  buyFormRef: Ref<QuickEntryFormExposed | undefined>,
  sellFormRef: Ref<QuickEntryFormExposed | undefined>,
  dividendFormRef?: Ref<QuickEntryFormExposed | undefined>
) {
  const submitting = ref(false);

  async function handleSubmit() {
    if (submitting.value) return;
    submitting.value = true;
    try {
      if (opType.value === "buy") await buyFormRef.value?.handleSubmit();
      else if (opType.value === "sell") await sellFormRef.value?.handleSubmit();
      else if (opType.value === "dividend")
        await dividendFormRef?.value?.handleSubmit();
    } finally {
      submitting.value = false;
    }
  }

  function emitRefresh() {
    emitter.emit("refresh-ledger-data");
  }

  function resetForms() {
    buyFormRef.value?.resetForm();
    sellFormRef.value?.resetForm();
    dividendFormRef?.value?.resetForm();
  }

  return { submitting, handleSubmit, emitRefresh, resetForms };
}
