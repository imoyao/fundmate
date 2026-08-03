import { ref, type Ref } from "vue";
import { getLedgers } from "@/api/ledger";
import { emitter } from "@/utils/mitt";

export function useQuickEntry(opts?: { autoLoad?: boolean }) {
  const ledgers = ref<any[]>([]);
  const loading = ref(false);

  async function loadLedgers() {
    loading.value = true;
    try {
      const res = await getLedgers();
      let data = (res as any)?.data;
      if (data && typeof data === "object" && !Array.isArray(data))
        data = data.data ?? data;
      ledgers.value = Array.isArray(data) ? data : [];
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
  opType: Ref<"buy" | "sell">,
  buyFormRef: Ref<any>,
  sellFormRef: Ref<any>
) {
  const submitting = ref(false);

  async function handleSubmit() {
    if (submitting.value) return;
    submitting.value = true;
    try {
      if (opType.value === "buy") await buyFormRef.value?.handleSubmit();
      else await sellFormRef.value?.handleSubmit();
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
  }

  return { submitting, handleSubmit, emitRefresh, resetForms };
}
