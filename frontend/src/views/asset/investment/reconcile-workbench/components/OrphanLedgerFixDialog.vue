<template>
  <el-dialog
    :model-value="modelValue"
    :title="`回填账本 · ${group?.resolved_ledger?.name || '缺账本流水'}`"
    width="620px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <OrphanLedgerFixResult
      v-if="result"
      :result="result"
      :undone="undone"
      :undoing="undoing"
      @undo="undo"
    />
    <template v-else>
      <p class="olf-lead">
        这些流水的账本为空，不进任何账户视图。先逐条核对「按账户名精确匹配到的目标账本」，再确认回填；写入可凭日志编号撤销。
      </p>

      <div v-if="group?.resolved_ledger" class="olf-target">
        目标账本：#{{ group.resolved_ledger.id }}
        <strong>{{ group.resolved_ledger.name }}</strong>
        <span>（{{ group?.transactions.length ?? 0 }} 条流水）</span>
      </div>

      <!-- 逐条归属必须真的展开看过：没点开就不许提交（准入判据在 orphanLedgerFixGuard） -->
      <div class="olf-preview">
        <div class="olf-preview__head">
          <span class="olf-preview__title">逐条归属核对</span>
          <el-button size="small" :disabled="previewSeen" @click="showPreview">
            {{ previewSeen ? "已展开" : "展开逐条明细" }}
          </el-button>
        </div>
        <p v-if="!previewSeen" class="olf-preview__empty">
          尚未展开。展开后请逐条核对账户名与目标账本，才能提交。
        </p>
        <ul v-else class="olf-rows">
          <li
            v-for="t in group?.transactions ?? []"
            :key="t.id"
            class="olf-row"
          >
            <span class="olf-row__id">#{{ t.id }}</span>
            <span>{{ t.txn_type }}</span>
            <span>{{ t.trade_date || "缺交易日期" }}</span>
            <span>{{ t.account_name || "缺账户名" }}</span>
            <span>{{ t.amount }} 元</span>
            <span v-if="t.block_reason" class="olf-row__block">
              {{ t.block_reason }}
            </span>
            <span v-else class="olf-row__ok">
              → 账本 #{{ t.resolved_ledger_id }}
            </span>
          </li>
        </ul>
      </div>

      <p class="olf-warn">
        本次只补全流水归属（<code>ledger_id</code>
        一列），系统不会改动持仓份额、金额与其它字段；也不会触发自动重挂。
      </p>

      <el-checkbox v-model="confirmed" class="olf-confirm">
        我已逐条核对，确认只回填账本、不改份额
      </el-checkbox>

      <el-form label-width="110px" size="default" class="olf-reason">
        <el-form-item label="原因（选填）">
          <el-input
            v-model="reason"
            placeholder="例如：按交割单核对账户名后回填"
          />
        </el-form-item>
      </el-form>
    </template>

    <template #footer>
      <span v-if="!result && blockReason" class="olf-block">{{
        blockReason
      }}</span>
      <el-button @click="emit('update:modelValue', false)">{{
        result ? "关闭" : "取消"
      }}</el-button>
      <el-button
        v-if="!result"
        type="primary"
        :disabled="!canSubmit"
        :loading="submitting"
        @click="submit"
      >
        确认回填
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  backfillOrphanLedgers,
  undoOrphanLedgerBackfill,
  type OrphanLedgerBackfillResult,
  type OrphanLedgerGroup
} from "@/api/reconciliation";
import {
  canSubmitOrphanBackfill,
  submitBlockReason
} from "../utils/orphanLedgerFixGuard";
import OrphanLedgerFixResult from "./OrphanLedgerFixResult.vue";

/** 缺账本流水回填向导（#2875）：逐条核对归属 → 二次确认 → 凭 log_id 撤销。 */
const props = defineProps<{
  modelValue: boolean;
  group: OrphanLedgerGroup | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const previewSeen = ref(false);
const confirmed = ref(false);
const reason = ref("");
const submitting = ref(false);
const result = ref<OrphanLedgerBackfillResult | null>(null);
const undoing = ref(false);
const undone = ref(false);

const guardInput = computed(() => ({
  group: props.group,
  previewSeen: previewSeen.value,
  confirmed: confirmed.value,
  submitting: submitting.value
}));
const blockReason = computed(() => submitBlockReason(guardInput.value));
const canSubmit = computed(() => canSubmitOrphanBackfill(guardInput.value));

/** 每次打开都从干净状态开始，避免上一组的「已看过 / 已确认」被复用到下一组 */
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    previewSeen.value = false;
    confirmed.value = false;
    reason.value = "";
    submitting.value = false;
    result.value = null;
    undoing.value = false;
    undone.value = false;
  }
);

function showPreview(): void {
  previewSeen.value = true;
}

async function submit(): Promise<void> {
  if (!canSubmit.value || !props.group) return;
  const ids = props.group.transactions.map(t => t.id);
  if (ids.length === 0) return;
  submitting.value = true;
  try {
    const res = await backfillOrphanLedgers({
      transaction_ids: ids,
      reason: reason.value || undefined
    });
    result.value = res.data ?? null;
    ElMessage.success("回填完成");
    emit("submitted");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err.response?.data?.message || "回填失败");
  } finally {
    submitting.value = false;
  }
}

async function undo(): Promise<void> {
  if (!result.value) return;
  undoing.value = true;
  try {
    await undoOrphanLedgerBackfill(result.value.log_id);
    undone.value = true;
    ElMessage.success("已撤销本次回填");
    emit("submitted");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err.response?.data?.message || "撤销失败");
  } finally {
    undoing.value = false;
  }
}
</script>

<style scoped>
.olf-lead,
.olf-warn,
.olf-target {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olf-target {
  padding: 8px 10px;
  margin: 0 0 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.olf-target strong {
  color: var(--color-primary-ink);
}

.olf-preview {
  padding: 10px 12px;
  margin-bottom: 10px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.olf-preview__head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.olf-preview__title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--color-primary-ink);
}

.olf-preview__empty {
  margin: 8px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olf-rows {
  padding-left: 18px;
  margin: 8px 0 0;
}

.olf-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 3px 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olf-row__id {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.olf-row__block {
  color: var(--color-warning-ink);
}

.olf-row__ok {
  font-variant-numeric: tabular-nums;
  color: var(--color-success-ink);
}

.olf-warn {
  padding: 8px 10px;
  color: var(--color-danger-ink);
  background: color-mix(in srgb, var(--color-danger-ink) 10%, transparent);
  border-radius: var(--radius-sm);
}

.olf-confirm {
  margin: 10px 0;
}

.olf-reason {
  margin-top: 4px;
}

.olf-block {
  margin-right: auto;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}
</style>
