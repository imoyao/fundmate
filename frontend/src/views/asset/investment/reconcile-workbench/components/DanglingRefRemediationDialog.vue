<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="560px"
    append-to-body
    @update:model-value="close"
  >
    <div v-if="result" class="dr-done">
      <p class="dr-done__title">
        {{ mode === "enrich" ? "已补全信息" : "已删除" }}
      </p>
      <p>
        {{ result.summary }}，日志编号 <strong>#{{ result.log_id }}</strong>
      </p>
      <p>可凭日志编号撤销本次处理。</p>
      <el-button
        v-if="!undone"
        type="danger"
        plain
        :loading="undoing"
        @click="undo"
      >
        撤销本次处理
      </el-button>
      <p v-else class="dr-done__undone">本次处理已撤销</p>
    </div>
    <template v-else>
      <p v-if="mode === 'enrich'" class="dr-lead">
        这些交易缺少标的代码或交易日期，找不到对应的持仓。补全信息后系统会重新检查，但未必立刻能补上关联——如仍缺持仓记录，还需补建持仓或补录流水。
      </p>
      <p v-else class="dr-lead">
        这些交易找不到对应的持仓记录。删除前请先核对明细，确认后才会写入。
      </p>
      <p v-if="mode === 'delete'" class="dr-static-warn">
        删除这些交易会影响已实现盈亏与收益统计；现存持仓份额不会改变；可凭日志编号撤销本次处理。
      </p>
      <template v-if="mode === 'enrich'">
        <el-form label-width="90px" size="default">
          <el-form-item label="标的代码">
            <el-input
              v-model="symbolInput"
              placeholder="例如 600519"
              maxlength="30"
            />
          </el-form-item>
          <el-form-item label="交易日期">
            <el-input v-model="tradeDateInput" type="date" />
          </el-form-item>
          <el-form-item label="原因（选填）">
            <el-input v-model="reason" placeholder="例如：按交割单核对后补全" />
          </el-form-item>
        </el-form>
        <div class="dr-preview-bar">
          <el-button
            size="small"
            :loading="previewing"
            @click="runEnrichPreview"
          >
            查看影响
          </el-button>
          <span v-if="enrichPreview" class="dr-preview-bar__hint"
            >已查看影响</span
          >
        </div>
        <DanglingRefRemediationPreview
          :mode="mode"
          :enrich-preview="enrichPreview"
          :delete-preview="deletePreview"
          :previewing="previewing"
        />
        <el-checkbox v-model="confirmed" class="dr-confirm"
          >我已核对，确认补全</el-checkbox
        >
      </template>
      <template v-else>
        <DanglingRefRemediationPreview
          :mode="mode"
          :enrich-preview="enrichPreview"
          :delete-preview="deletePreview"
          :previewing="previewing"
        />
        <el-form label-width="90px" size="default">
          <el-form-item label="确认词">
            <el-input
              v-model="confirmPhrase"
              placeholder="请输入「删除」二字确认"
            />
          </el-form-item>
          <el-form-item label="原因（选填）">
            <el-input v-model="reason" placeholder="例如：重复导入的流水" />
          </el-form-item>
        </el-form>
      </template>
    </template>
    <template #footer>
      <span v-if="!result && blockReason" class="dr-block">{{
        blockReason
      }}</span>
      <el-button @click="close(false)">{{
        result ? "关闭" : "取消"
      }}</el-button>
      <el-button
        v-if="!result"
        :type="mode === 'delete' ? 'danger' : 'primary'"
        :disabled="!canSubmit"
        :loading="submitting"
        @click="submit"
      >
        {{ mode === "enrich" ? "确认补全" : "确认删除" }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
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
import DanglingRefRemediationPreview from "./DanglingRefRemediationPreview.vue";
/** 数据缺失分组「补全信息 / 删除」向导（#2866 后续）：准入判据全走 guard。 */
const props = defineProps<{
  modelValue: boolean;
  group: DanglingRefGroup | null;
  mode: "enrich" | "delete";
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();
interface DoneResult {
  log_id: number;
  summary: string;
}
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
  (props.group?.transactions ?? []).map(t => t.id)
);
const txnCount = computed(() => transactionIds.value.length);
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
  props.mode === "enrich"
    ? enrichBlockReason(enrichGuard.value)
    : deleteBlockReason(deleteGuard.value)
);
const canSubmit = computed(() =>
  props.mode === "enrich"
    ? canSubmitEnrich(enrichGuard.value)
    : canSubmitDelete(deleteGuard.value)
);
const dialogTitle = computed(() =>
  props.mode === "enrich"
    ? `补全信息 · ${props.group?.symbol || "数据缺失"}`
    : `删除交易 · ${props.group?.symbol || "数据缺失"}`
);
/** 统一从 HTTP 错误里取后端 message，避免在新文件里写显式 any。 */
function errorMessage(e: unknown, fallback: string): string {
  return (
    (e as { response?: { data?: { message?: string } } } | null)?.response?.data
      ?.message || fallback
  );
}
function close(value: boolean): void {
  emit("update:modelValue", value);
}
/** 每次打开都从干净状态开始，避免上一次的预览/结果被复用到另一组。 */
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
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
    if (props.mode === "delete") void runDeletePreview();
  }
);
/** 输入一变即作废旧预览；guard 的 fieldSignature 比对是第二层。 */
watch([symbolInput, tradeDateInput], () => {
  enrichPreview.value = null;
  confirmed.value = false;
});
async function runEnrichPreview(): Promise<void> {
  if (!hasField.value || previewing.value || !props.group) return;
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
  if (!props.group) return;
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
  if (!canSubmit.value || !props.group) return;
  submitting.value = true;
  try {
    if (props.mode === "enrich") {
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
    emit("submitted");
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
    if (props.mode === "enrich") {
      await undoDanglingRefEnrich(result.value.log_id);
    } else {
      await undoDanglingRefDelete(result.value.log_id);
    }
    undone.value = true;
    ElMessage.success("已撤销本次处理");
    emit("submitted");
  } catch (e: unknown) {
    ElMessage.error(errorMessage(e, "撤销失败"));
  } finally {
    undoing.value = false;
  }
}
</script>
<style scoped>
.dr-lead,
.dr-done p,
.dr-preview-bar__hint,
.dr-block {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.dr-static-warn {
  padding: 8px 10px;
  margin: 8px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-danger-ink);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.dr-preview-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 4px 0 10px;
}

.dr-preview-bar__hint {
  color: var(--color-success-ink);
}

.dr-confirm {
  margin-top: 4px;
}

.dr-block {
  margin-right: auto;
  color: var(--color-warning-ink);
}

.dr-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.dr-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
