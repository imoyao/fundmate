<template>
  <el-dialog
    :model-value="modelValue"
    :title="`改挂到正确标的 · ${heading}`"
    width="min(560px, 92vw)"
    append-to-body
    @update:model-value="close"
  >
    <div class="drm-body">
      <!-- 结果态：就地替换预览；撤销是唯一后续写动作 -->
      <div v-if="result" class="drm-done">
        <p class="drm-done__title">已改挂</p>
        <p>
          {{ result.txn_count }} 笔流水现在挂在
          {{ reconAssetHeading(result.symbol, result.display_name) }}
          （{{ reconRecordRef(result.position_id) }}）。
        </p>
        <p v-if="result.created_position_id !== null">
          这条持仓是新按流水建的：{{ reconQuantity(result.quantity) }}，成本均价
          {{ resultAvgPrice }} 元。
        </p>
        <p v-else>这是既有持仓，只改了流水的归属，份额没有变动。</p>
        <p class="drm-done__log">
          日志编号 <strong>#{{ result.log_id }}</strong>
        </p>
        <p v-if="undoSkippedNote" class="drm-done__skip">
          {{ undoSkippedNote }}
        </p>
        <el-button
          v-if="!undone && !undoSkippedNote"
          type="danger"
          plain
          :loading="undoing"
          @click="undo"
        >
          撤销此次改挂
        </el-button>
        <p v-else-if="undone" class="drm-done__undone">此次改挂已撤销</p>
      </div>

      <template v-else>
        <p v-if="previewing" class="drm-loading">正在核对流水归属…</p>
        <template v-else-if="preview">
          <div class="drm-facts">
            <p>标的：{{ heading }}</p>
            <p>现在挂在：{{ wrongLabel }}</p>
            <p v-if="preview.target_position">
              将改挂到：{{
                reconAssetHeading(
                  preview.target_position.symbol,
                  preview.target_position.name
                )
              }}
              （{{ reconRecordRef(preview.target_position.id) }}），现有
              {{ reconQuantity(preview.target_position.quantity) }}
            </p>
            <p v-else>
              将按这 {{ preview.txn_count }} 笔流水新建一条持仓：净份额
              {{ reconQuantity(preview.net_units) }}，成本均价
              {{ previewAvgPrice }} 元{{ avgPriceNote }}
            </p>
          </div>
          <!-- 份额不会被自动重算，是这次动作的后果，必须在提交前说一次 -->
          <p v-if="shareNote" class="drm-share">{{ shareNote }}</p>
          <p v-if="!preview.fixable" class="drm-block">
            {{ preview.block_reason || "这批流水暂不能改挂" }}
          </p>
          <el-form label-width="90px" size="default">
            <el-form-item label="原因（选填）">
              <el-input
                v-model="reason"
                placeholder="例如：导入时挂错了标的，改挂回去"
              />
            </el-form-item>
          </el-form>
        </template>
        <p v-else-if="previewError" class="drm-block">{{ previewError }}</p>
      </template>
    </div>
    <template #footer>
      <span v-if="!result && blockNote" class="drm-footer__block">{{
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
        <span class="drm-footer__submit">
          <el-button
            type="primary"
            :disabled="!canSubmit"
            :loading="submitting"
            @click="submit"
          >
            确认改挂
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
import { formatPrice } from "@/utils/pricePrecision";
import {
  fixMislinkedRefs,
  previewMislinkedRefFix,
  undoMislinkedRefFix,
  type DanglingRefGroup,
  type MislinkedRefFixResult,
  type MislinkedRefPreview,
  type MislinkedRefUndoResult
} from "@/api/reconciliation";
import { useNestedDialog } from "../composables/useNestedDialog";
import {
  reconAssetHeading,
  reconQuantity,
  reconRecordRef
} from "../utils/reconDisplay";

/**
 * 域 F「挂错标的」的唯一写路径：预览（自动拉取）→ 确认改挂 → 凭 log_id 撤销。
 *
 * 这类流水 `position_id` 指着的持仓**存在**、只是标的对不上：既进不了
 * 「回补关联」（要求悬空），也进不了「按流水重建」（前置同样是悬空），
 * 所以在后端修好之前它们永远 pending、且没有任何入口。
 *
 * 后端只有一条修法（同账本有同标的持仓 ⇒ 只改指针；没有 ⇒ 按流水新建），
 * 前端不提供「只摘下来」的半个动作 —— 摘下来只是把脏数据换成悬空数据。
 */
const props = defineProps<{
  modelValue: boolean;
  group: DanglingRefGroup | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  fixed: [];
}>();

const preview = ref<MislinkedRefPreview | null>(null);
const previewing = ref(false);
const previewError = ref("");
const reason = ref("");
const submitting = ref(false);
const result = ref<MislinkedRefFixResult | null>(null);
const undoing = ref(false);
const undone = ref(false);
const undoResult = ref<MislinkedRefUndoResult | null>(null);

const transactionIds = computed(() =>
  (props.group?.transactions ?? []).map(t => t.id)
);

/** 加载中回退到组本身的 symbol；有预览后用预览的名称 + 代码 */
const heading = computed(() =>
  preview.value
    ? reconAssetHeading(preview.value.symbol, preview.value.display_name)
    : reconAssetHeading(props.group?.symbol)
);

/** 现在挂在哪：优先用组上的持仓快照（列表已带），预览回来后以预览为准 */
const wrongLabel = computed(() => {
  const labels = (props.group?.wrong_positions ?? []).map(
    p => `${p.symbol || "标的代码未填"}（${reconRecordRef(p.id)}）`
  );
  return labels.length ? labels.join("、") : "别的标的的持仓";
});

/** 价格位数走唯一真源 pricePrecision，不手写 toFixed */
const previewAvgPrice = computed(() =>
  formatPrice(preview.value?.avg_price, preview.value?.asset_type)
);
const resultAvgPrice = computed(() =>
  formatPrice(result.value?.avg_price, preview.value?.asset_type)
);

/** 成本均价为 0 的后果贴在值上说一次（后端 warnings 第 4 条的现场化） */
const avgPriceNote = computed(() =>
  preview.value?.avg_price === 0 ? "（组内没有买入流水，需在持仓页补成本）" : ""
);

/** 「原持仓份额不会自动重算」是点下去之后的后果，提交前必须看见 */
const shareNote = computed(() => {
  const warning = preview.value?.warnings?.find(w => w.includes("重算"));
  return warning ?? "";
});

/** 不可改挂时给出可执行的下一步（后端原文），不只把按钮置灰让人猜 */
const blockNote = computed(() => {
  if (previewing.value) return "正在生成预览";
  if (previewError.value) return previewError.value;
  if (!preview.value) return "";
  if (!preview.value.fixable)
    return preview.value.block_reason || "这批流水暂不能改挂";
  return "";
});

const canSubmit = computed(
  () =>
    !!preview.value?.fixable &&
    !previewing.value &&
    !previewError.value &&
    transactionIds.value.length > 0
);

/** 撤销被跳过 ≠ 撤销成功：把后端原因原样亮出来，数据保持改挂后的状态 */
const undoSkippedNote = computed(() => {
  if (!undoResult.value?.skipped) return "";
  return (
    undoResult.value.skip_reason ||
    "未能自动撤销：数据在改挂后已被改动，本次保持现状"
  );
});

/** 抽屉内打开时登记给抽屉，避免两层遮罩叠加；不在抽屉内则静默跳过。 */
useNestedDialog(toRef(props, "modelValue"));

/** 每次打开都从干净状态开始，并立即拉预览（fixable=false 是正常返回） */
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
  if (!transactionIds.value.length) {
    previewError.value = "这组流水为空，无法改挂";
    return;
  }
  previewing.value = true;
  try {
    const res = await previewMislinkedRefFix(transactionIds.value);
    preview.value = res.data ?? null;
    if (!res.data) previewError.value = "预览没有返回数据";
  } catch (e) {
    previewError.value = errorMessageOf(e) || "预览失败";
  } finally {
    previewing.value = false;
  }
}

async function submit(): Promise<void> {
  // 纵深防御：后端会硬校验 confirm，前端也不许把不可改挂的组提交出去
  if (!canSubmit.value || !props.group) return;
  submitting.value = true;
  try {
    const res = await fixMislinkedRefs({
      transaction_ids: transactionIds.value,
      reason: reason.value || undefined,
      confirm: true
    });
    result.value = res.data ?? null;
    if (!res.data) {
      ElMessage.error("改挂没有返回结果");
      return;
    }
    ElMessage.success("已改挂到正确标的");
    emit("fixed");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "改挂失败");
  } finally {
    submitting.value = false;
  }
}

async function undo(): Promise<void> {
  if (!result.value) return;
  undoing.value = true;
  try {
    const res = await undoMislinkedRefFix(result.value.log_id);
    undoResult.value = res.data ?? null;
    if (res.data?.skipped) {
      ElMessage.warning(res.data.skip_reason || "未能撤销：数据期间已被改动");
      emit("fixed");
      return;
    }
    undone.value = true;
    ElMessage.success("此次改挂已撤销");
    emit("fixed");
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
.drm-loading {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.drm-facts {
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

.drm-facts p {
  margin: 0;
}

.drm-share {
  padding: 8px 10px;
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-info-ink);
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.drm-block {
  padding: 8px 10px;
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.drm-footer__block {
  margin-right: auto;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}

.drm-footer__submit {
  display: inline-flex;
  margin-left: 8px;
}

.drm-done p {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.drm-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.drm-done__log {
  font-variant-numeric: tabular-nums;
}

.drm-done__skip {
  padding: 6px 10px;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.drm-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
