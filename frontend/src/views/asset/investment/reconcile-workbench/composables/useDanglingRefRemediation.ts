/**
 * 「数据缺失」补全 / 删除向导的状态与写路径（#2866 后续）。
 *
 * 从 `DanglingRefRemediationDialog.vue` 抽出：弹窗文件只负责摆组件，
 * 准入判据仍在 `danglingRefRemediationGuard`，展示态翻译在 `enrichSteps`，
 * 本文件只管表单状态、预览 / 提交 / 撤销的 API 调用与重置时机。
 *
 * 页面规模门禁阈值 400 行：逻辑留在这里，弹窗 SFC 不要长回去。
 */
import { computed, ref, watch, type Ref } from "vue";
import { ElMessage } from "element-plus";
import {
  previewDanglingRefEnrich,
  enrichDanglingRefs,
  undoDanglingRefEnrich,
  previewDanglingRefDelete,
  deleteDanglingRefs,
  undoDanglingRefDelete,
  type DanglingRefGroup,
  type DanglingRefEnrichPreview,
  type DanglingRefDeletePreview
} from "@/api/reconciliation";
import {
  buildFieldSignature,
  canSubmitDelete,
  canSubmitEnrich,
  deleteBlockReason,
  enrichBlockReason,
  type DeleteGuardInput,
  type EnrichGuardInput
} from "../utils/danglingRefRemediationGuard";
import { inspectGroupNeeds } from "../utils/danglingRefEnrichScope";
import { describeEnrichSteps } from "../utils/enrichSteps";

interface DoneResult {
  log_id: number;
  summary: string;
}

interface RemediationOptions {
  group: Ref<DanglingRefGroup | null>;
  mode: Ref<"enrich" | "delete">;
  open: Ref<boolean>;
  onSubmitted: () => void;
}

/** 统一从 HTTP 错误里取后端 message，避免显式 any。 */
function errorMessage(e: unknown, fallback: string): string {
  return (
    (e as { response?: { data?: { message?: string } } } | null)?.response?.data
      ?.message || fallback
  );
}

export function useDanglingRefRemediation(options: RemediationOptions) {
  const { group, mode, open, onSubmitted } = options;
  const symbolInput = ref("");
  const tradeDateInput = ref("");
  const reason = ref("");
  const confirmed = ref(false);
  const confirmPhrase = ref("");
  const enrichPreview = ref<DanglingRefEnrichPreview | null>(null);
  const deletePreview = ref<DanglingRefDeletePreview | null>(null);
  const previewing = ref(false);
  const submitting = ref(false);
  const undoing = ref(false);
  const undone = ref(false);
  const result = ref<DoneResult | null>(null);
  const transactionIds = computed(() =>
    (group.value?.transactions ?? []).map(t => t.id)
  );
  const txnCount = computed(() => transactionIds.value.length);
  /**
   * 这组还缺什么。判据在 `danglingRefEnrichScope`（纯函数 + 单测），这里只做装配：
   * 有代码的组不给「标的代码」输入框，全齐的组直接挡在提交前。
   */
  const needs = computed(() =>
    inspectGroupNeeds(group.value?.transactions ?? [])
  );
  const needsFill = computed(
    () => !needs.value.complete && needs.value.txnCount > 0
  );
  const hasField = computed(
    () => !!(symbolInput.value.trim() || tradeDateInput.value)
  );
  const fieldSignature = computed(() =>
    buildFieldSignature(
      symbolInput.value.trim() || null,
      tradeDateInput.value || null
    )
  );
  const enrichGuard = computed<EnrichGuardInput>(() => ({
    preview: enrichPreview.value,
    hasField: hasField.value,
    needsFill: needsFill.value,
    fieldSignature: fieldSignature.value,
    confirmed: confirmed.value,
    previewing: previewing.value,
    submitting: submitting.value,
    txnCount: txnCount.value
  }));
  const deleteGuard = computed<DeleteGuardInput>(() => ({
    preview: deletePreview.value,
    confirmPhrase: confirmPhrase.value,
    previewing: previewing.value,
    submitting: submitting.value,
    txnCount: txnCount.value
  }));
  const blockReason = computed(() =>
    mode.value === "enrich"
      ? enrichBlockReason(enrichGuard.value)
      : deleteBlockReason(deleteGuard.value)
  );
  const canSubmit = computed(() =>
    mode.value === "enrich"
      ? canSubmitEnrich(enrichGuard.value)
      : canSubmitDelete(deleteGuard.value)
  );
  const stepState = computed(() => describeEnrichSteps(enrichGuard.value));

  /** 每次打开都从干净状态开始，避免上一次的预览/结果被复用到另一组。 */
  watch(open, isOpen => {
    if (!isOpen) return;
    symbolInput.value = "";
    tradeDateInput.value = "";
    reason.value = "";
    confirmed.value = false;
    confirmPhrase.value = "";
    enrichPreview.value = null;
    deletePreview.value = null;
    previewing.value = false;
    submitting.value = false;
    undoing.value = false;
    undone.value = false;
    result.value = null;
    if (mode.value === "delete") void runDeletePreview();
  });

  /** 输入一变即作废旧预览；guard 的 fieldSignature 比对是第二层。 */
  watch([symbolInput, tradeDateInput], () => {
    enrichPreview.value = null;
    confirmed.value = false;
  });

  async function runEnrichPreview(): Promise<void> {
    if (!hasField.value || previewing.value || !group.value) return;
    previewing.value = true;
    enrichPreview.value = null;
    try {
      const res = await previewDanglingRefEnrich({
        transaction_ids: transactionIds.value,
        symbol: symbolInput.value.trim() || undefined,
        trade_date: tradeDateInput.value || undefined
      });
      const p = res.data;
      if (p) {
        // 后端 trade_date 是 iso 串、与前端 YYYY-MM-DD 输入格式不同；回填请求时的输入，
        // 避免 guard 的 fieldSignature 比对被格式差误判成「输入已变化」。
        enrichPreview.value = {
          ...p,
          symbol: symbolInput.value.trim() || null,
          trade_date: tradeDateInput.value || null
        };
      }
    } catch (e: unknown) {
      ElMessage.error(errorMessage(e, "查看影响失败"));
    } finally {
      previewing.value = false;
    }
  }

  async function runDeletePreview(): Promise<void> {
    if (!group.value) return;
    previewing.value = true;
    deletePreview.value = null;
    try {
      const res = await previewDanglingRefDelete({
        transaction_ids: transactionIds.value
      });
      deletePreview.value = res.data ?? null;
    } catch (e: unknown) {
      ElMessage.error(errorMessage(e, "查看影响失败"));
    } finally {
      previewing.value = false;
    }
  }

  async function submit(): Promise<void> {
    if (!canSubmit.value || !group.value) return;
    submitting.value = true;
    try {
      if (mode.value === "enrich") {
        const r = (
          await enrichDanglingRefs({
            transaction_ids: transactionIds.value,
            symbol: symbolInput.value.trim() || undefined,
            trade_date: tradeDateInput.value || undefined,
            reason: reason.value || undefined,
            confirm: true
          })
        ).data;
        result.value = {
          log_id: r.log_id,
          summary: `已补全 ${r.updated} 条交易的信息`
        };
        ElMessage.success("已补全信息");
      } else {
        const r = (
          await deleteDanglingRefs({
            transaction_ids: transactionIds.value,
            reason: reason.value || undefined,
            confirm: true,
            confirm_phrase: confirmPhrase.value
          })
        ).data;
        result.value = {
          log_id: r.log_id,
          summary: `已删除 ${r.deleted} 条交易`
        };
        ElMessage.success("已删除");
      }
      onSubmitted();
    } catch (e: unknown) {
      ElMessage.error(errorMessage(e, "提交失败"));
    } finally {
      submitting.value = false;
    }
  }

  async function undo(): Promise<void> {
    if (!result.value) return;
    undoing.value = true;
    try {
      if (mode.value === "enrich") {
        await undoDanglingRefEnrich(result.value.log_id);
      } else {
        await undoDanglingRefDelete(result.value.log_id);
      }
      undone.value = true;
      ElMessage.success("已撤销本次处理");
      onSubmitted();
    } catch (e: unknown) {
      ElMessage.error(errorMessage(e, "撤销失败"));
    } finally {
      undoing.value = false;
    }
  }

  return {
    symbolInput,
    tradeDateInput,
    reason,
    confirmed,
    confirmPhrase,
    enrichPreview,
    deletePreview,
    previewing,
    submitting,
    undoing,
    undone,
    result,
    txnCount,
    needs,
    needsFill,
    hasField,
    stepState,
    blockReason,
    canSubmit,
    runEnrichPreview,
    submit,
    undo
  };
}
