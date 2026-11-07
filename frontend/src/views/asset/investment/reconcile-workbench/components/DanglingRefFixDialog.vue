<template>
  <el-dialog
    :model-value="modelValue"
    :title="`补上关联 · ${group?.symbol || '数据缺失'}`"
    width="560px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <DanglingRefFixResult
      v-if="result"
      :result="result"
      :undone="undone"
      :undoing="undoing"
      @undo="undo"
    />
    <template v-else>
      <p class="dfd-lead">
        这些交易找不到对应的持仓记录。先选好它应该归到哪笔持仓、看清改动预览，
        确认后才写入；写错了可以凭日志编号撤销。
      </p>
      <el-form label-width="110px" size="default">
        <el-form-item label="归到哪笔持仓">
          <el-select
            v-model="selectedPositionId"
            placeholder="从候选持仓中选择"
            style="width: 100%"
            @change="onTargetChange"
          >
            <el-option
              v-for="c in group?.candidates ?? []"
              :key="c.id"
              :label="`#${c.id} ${c.symbol} · ${c.quantity} 份 · ${c.ownership_status}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="原因（选填）">
          <el-input v-model="reason" placeholder="例如：按交割单核对后补上" />
        </el-form-item>
      </el-form>
      <p class="dfd-warn">
        本次只改交易的归属，不会自动改动持仓份额。补完后如需让份额与流水对齐，请到持仓页手动重算。
      </p>
      <DanglingRefPreviewPanel
        :preview="preview"
        :previewing="previewing"
        :can-preview="selectedPositionId != null"
        @preview="runPreview"
      />
    </template>
    <template #footer>
      <span v-if="!result && blockReason" class="dfd-block">{{
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
        确认补上
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  previewDanglingRefReattach,
  reattachDanglingRefs,
  undoDanglingRefReattach,
  type DanglingRefGroup,
  type DanglingRefPreview,
  type DanglingRefReattachResult
} from "@/api/reconciliation";
import {
  canSubmitReattach,
  submitBlockReason
} from "../utils/danglingRefFixGuard";
import DanglingRefPreviewPanel from "./DanglingRefPreviewPanel.vue";
import DanglingRefFixResult from "./DanglingRefFixResult.vue";

/** 悬空引用修复向导（#2866）：预览 → 确认回补 → 凭 log_id 撤销，未展示预览不许写。 */
const props = defineProps<{
  modelValue: boolean;
  group: DanglingRefGroup | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const selectedPositionId = ref<number | null>(null);
const reason = ref("");
const preview = ref<DanglingRefPreview | null>(null);
const previewing = ref(false);
const submitting = ref(false);
const result = ref<DanglingRefReattachResult | null>(null);
const undoing = ref(false);
const undone = ref(false);
const transactionIds = computed(() =>
  (props.group?.transactions ?? []).map(t => t.id)
);
const guardInput = computed(() => ({
  preview: preview.value,
  targetSelected: selectedPositionId.value != null,
  previewing: previewing.value,
  submitting: submitting.value
}));
const blockReason = computed(() => submitBlockReason(guardInput.value));
const canSubmit = computed(() => canSubmitReattach(guardInput.value));

/** 每次打开都从干净状态开始，避免上一次的预览/结果被复用到另一组 */
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    selectedPositionId.value = null;
    reason.value = "";
    preview.value = null;
    previewing.value = false;
    submitting.value = false;
    result.value = null;
    undoing.value = false;
    undone.value = false;
  }
);
/** 换目标持仓即作废旧预览，绝不拿 A 持仓的份额预估去提交 B 持仓 */
function onTargetChange(): void {
  preview.value = null;
}
async function runPreview(): Promise<void> {
  if (selectedPositionId.value == null || !props.group) return;
  previewing.value = true;
  preview.value = null;
  try {
    const res = await previewDanglingRefReattach({
      transaction_ids: transactionIds.value,
      target_position_id: selectedPositionId.value
    });
    preview.value = res.data ?? null;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "预览失败");
  } finally {
    previewing.value = false;
  }
}
async function submit(): Promise<void> {
  // 纵深防御：后端会硬校验 symbol / 目标持仓，前端也不许把不可回补的组提交出去
  if (
    !canSubmit.value ||
    selectedPositionId.value == null ||
    !props.group?.fixable
  )
    return;
  submitting.value = true;
  try {
    const res = await reattachDanglingRefs({
      transaction_ids: transactionIds.value,
      target_position_id: selectedPositionId.value,
      reason: reason.value || undefined
    });
    result.value = res.data ?? null;
    ElMessage.success("已补上关联");
    emit("submitted");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "补上关联失败");
  } finally {
    submitting.value = false;
  }
}
async function undo(): Promise<void> {
  if (!result.value) return;
  undoing.value = true;
  try {
    await undoDanglingRefReattach(result.value.log_id);
    undone.value = true;
    ElMessage.success("已撤销本次处理");
    emit("submitted");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "撤销失败");
  } finally {
    undoing.value = false;
  }
}
</script>

<style scoped>
.dfd-lead {
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.dfd-warn {
  padding: 8px 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-danger-ink);
  background: color-mix(in srgb, var(--color-danger-ink) 10%, transparent);
  border-radius: var(--radius-sm);
}

.dfd-block {
  margin-right: auto;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}
</style>
