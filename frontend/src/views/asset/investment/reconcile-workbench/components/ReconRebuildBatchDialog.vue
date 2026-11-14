<template>
  <el-dialog
    :model-value="modelValue"
    title="批量重建持仓"
    width="min(560px, 92vw)"
    append-to-body
    @update:model-value="close"
  >
    <div class="drbb-body">
      <!-- ③ 结果态：就地替换预览；撤销是唯一后续写动作 -->
      <div v-if="result" class="drbb-done">
        <p class="drbb-done__title">
          已重建 {{ result.rebuilt.length }} 组持仓
        </p>
        <p v-if="result.skipped.length">
          另有 {{ reconCount(result.skipped.length, "组") }}未重建：{{
            skipSummary
          }}
        </p>
        <p class="drbb-done__log">
          {{ reconCount(result.log_ids.length) }}撤销记录
        </p>
        <p v-if="undoSkippedNote" class="drbb-done__skip">
          {{ undoSkippedNote }}
        </p>
        <el-button
          v-if="!undone && !undoSkippedNote"
          type="danger"
          plain
          :loading="undoing"
          @click="undo"
        >
          撤销这次重建
        </el-button>
        <p v-else-if="undone" class="drbb-done__undone">这次重建已撤销</p>
      </div>
      <template v-else>
        <!-- 预览只给「会发生什么」的规模：90 组的逐行清单不是决策依据，
             账本分布 + 跳过原因是。逐组细节留在各自的阶段列表里。 -->
        <p v-if="previewing" class="drbb-loading">
          正在核对流水，生成重建预览…
        </p>
        <template v-else-if="preview">
          <div class="drbb-facts">
            <p>
              将重建 {{ reconCount(preview.rebuildable_count, "组") }} ·
              {{ reconCount(preview.txn_count) }}流水
            </p>
            <p v-if="ledgerSummary">账本：{{ ledgerSummary }}</p>
            <p v-if="preview.blocked_count" class="drbb-facts__block">
              另有 {{ reconCount(preview.blocked_count, "组") }}会跳过：{{
                blockSummary
              }}
            </p>
          </div>
          <el-form label-width="90px" size="default">
            <el-form-item label="原因（选填）">
              <el-input
                v-model="reason"
                placeholder="例如：旧版清仓删除了持仓行，按流水重建"
              />
            </el-form-item>
          </el-form>
        </template>
        <p v-else-if="previewError" class="drbb-block">{{ previewError }}</p>
      </template>
    </div>
    <template #footer>
      <span v-if="!result && blockNote" class="drbb-footer__block">{{
        blockNote
      }}</span>
      <el-button @click="close(false)">{{
        result ? "关闭" : "取消"
      }}</el-button>
      <el-tooltip
        v-if="!result"
        :content="blockNote || '可以提交'"
        :disabled="canSubmit"
        placement="top"
      >
        <span class="drbb-footer__submit">
          <el-button
            type="primary"
            :disabled="!canSubmit"
            :loading="submitting"
            @click="submit"
          >
            确认重建 {{ preview ? preview.rebuildable_count : 0 }} 组
          </el-button>
        </span>
      </el-tooltip>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from "vue";
import { ElMessage } from "element-plus";
import { errorMessageOf } from "@/utils/errorMessage";
import {
  previewDanglingRefRebuildBatch,
  rebuildDanglingRefPositionBatch,
  undoDanglingRefRebuildBatch,
  type DanglingRefBatchPreview,
  type DanglingRefBatchRebuildResult,
  type DanglingRefBatchUndoResult
} from "@/api/reconciliation";
import { useNestedDialog } from "../composables/useNestedDialog";
import { reconCount, reconLedgerName } from "../utils/reconDisplay";

/**
 * 域 F「按流水重建持仓」的批量档（2026-11-14）。
 *
 * 为什么需要它：真库 rebuild 阶段实测 90 组，逐组「预览 → 确认」= 180 次往返，
 * 而组与组之间用户没有任何决策点（每组的前置判据后端已经判完）。批量只把往返
 * 压成 2 次，**校验强度一条不降**——后端仍逐组跑同一份 plan、每组一条审计日志。
 *
 * 边界：不可重建的组不静默消失。预览阶段报「会跳过 N 组 + 原因」，
 * 写入后报「未重建 N 组 + 原因」，两次都用后端原话。
 */
const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  rebuilt: [];
}>();

const preview = ref<DanglingRefBatchPreview | null>(null);
const previewing = ref(false);
const previewError = ref("");
const reason = ref("");
const submitting = ref(false);
const result = ref<DanglingRefBatchRebuildResult | null>(null);
const undoing = ref(false);
const undone = ref(false);
const undoResult = ref<DanglingRefBatchUndoResult | null>(null);

/** 抽屉内打开时登记给抽屉，避免两层遮罩叠加；不在抽屉内则静默跳过。 */
useNestedDialog(toRef(props, "modelValue"));

/** 可重建组 → 写入端点要的 `groups`（每组一份流水 id，原样回传） */
const submitGroups = computed(() =>
  (preview.value?.groups ?? [])
    .filter(g => g.rebuildable)
    .map(g => g.transaction_ids)
);

/** 账本分布：超过 3 个只报数量，不把 90 组摊成一张清单 */
const ledgerSummary = computed(() => {
  const names = (preview.value?.groups ?? [])
    .filter(g => g.rebuildable)
    .map(g => reconLedgerName(g.ledger_name));
  const uniq = [...new Set(names.filter(Boolean))];
  if (uniq.length <= 3) return uniq.join("、");
  return `${uniq.slice(0, 3).join("、")} 等 ${uniq.length} 个`;
});

/** 同一原因只出现一次，前面带组数——90 行「同账本已有持仓行」读起来等于没有信息 */
function reasonSummary(
  rows: Array<{ reason?: string | null; block_reason?: string | null }>
): string {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const text = (row.reason ?? row.block_reason ?? "").trim();
    if (!text) continue;
    counts.set(text, (counts.get(text) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([text, n]) => (n > 1 ? `${text}（${n} 组）` : text))
    .join("；");
}

const blockSummary = computed(() =>
  reasonSummary(
    (preview.value?.groups ?? [])
      .filter(g => !g.rebuildable)
      .map(g => ({ block_reason: g.block_reason }))
  )
);

const skipSummary = computed(() => reasonSummary(result.value?.skipped ?? []));

/** 撤销被跳过 ≠ 撤销成功：把后端原因原样亮出来，数据保持重建后的状态 */
const undoSkippedNote = computed(() => {
  const skipped = undoResult.value?.skipped ?? 0;
  if (!skipped) return "";
  const first = undoResult.value?.results?.find(r => r.skip_reason);
  return (
    first?.skip_reason ||
    `${reconCount(skipped, "组")}在重建后已被改动，本次保持现状`
  );
});

/** 不可提交时给出可执行的下一步（后端原文），不只把按钮置灰让人猜 */
const blockNote = computed(() => {
  if (previewing.value) return "正在生成预览";
  if (previewError.value) return previewError.value;
  if (!preview.value) return "";
  if (!preview.value.rebuildable_count) return "这轮扫描没有可重建的组";
  return "";
});

const canSubmit = computed(
  () =>
    !!preview.value?.rebuildable_count &&
    !previewing.value &&
    !previewError.value &&
    submitGroups.value.length > 0
);

/** 每次打开都从干净状态开始，并立即拉预览（0 组是正常返回） */
watch(
  () => props.modelValue,
  open => {
    if (!open) return;
    preview.value = null;
    previewError.value = "";
    reason.value = "";
    submitting.value = false;
    result.value = null;
    undoing.value = false;
    undone.value = false;
    undoResult.value = null;
    void runPreview();
  }
);

async function runPreview(): Promise<void> {
  previewing.value = true;
  try {
    const res = await previewDanglingRefRebuildBatch();
    preview.value = res.data ?? null;
    if (!res.data) previewError.value = "预览没有返回数据";
  } catch (e) {
    previewError.value = errorMessageOf(e) || "预览失败";
  } finally {
    previewing.value = false;
  }
}

async function submit(): Promise<void> {
  // 纵深防御：后端会硬校验 confirm，前端也不许把 0 组提交出去
  if (!canSubmit.value) return;
  submitting.value = true;
  try {
    const res = await rebuildDanglingRefPositionBatch({
      groups: submitGroups.value,
      reason: reason.value || undefined,
      confirm: true
    });
    result.value = res.data ?? null;
    if (!res.data) {
      ElMessage.error("重建没有返回结果");
      return;
    }
    ElMessage.success(`已重建 ${res.data.rebuilt.length} 组持仓`);
    emit("rebuilt");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "批量重建失败");
  } finally {
    submitting.value = false;
  }
}

async function undo(): Promise<void> {
  const logIds = result.value?.log_ids ?? [];
  if (!logIds.length) return;
  undoing.value = true;
  try {
    const res = await undoDanglingRefRebuildBatch(logIds);
    undoResult.value = res.data ?? null;
    if (res.data?.skipped) {
      ElMessage.warning(undoSkippedNote.value || "部分重建未能撤销");
      emit("rebuilt");
      return;
    }
    undone.value = true;
    ElMessage.success("这次重建已撤销");
    emit("rebuilt");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "撤销失败");
  } finally {
    undoing.value = false;
  }
}

function close(value: boolean): void {
  emit("update:modelValue", value);
}
</script>

<style scoped>
.drbb-loading {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.drbb-facts {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  margin-bottom: 10px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 1.7;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.drbb-facts p {
  margin: 0;
}

.drbb-facts__block {
  color: var(--color-warning-ink);
}

.drbb-block {
  padding: 8px 10px;
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.drbb-footer__block {
  margin-right: auto;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}

.drbb-footer__submit {
  display: inline-flex;
  margin-left: 8px;
}

.drbb-done p {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.drbb-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.drbb-done__log {
  font-variant-numeric: tabular-nums;
}

.drbb-done__skip {
  padding: 6px 10px;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.drbb-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
