<template>
  <el-dialog
    :model-value="modelValue"
    :title="`重建持仓 · ${heading}`"
    width="min(560px, 92vw)"
    append-to-body
    @update:model-value="close"
  >
    <div class="drb-body">
      <!-- ③ 结果态：就地替换预览；撤销是唯一后续写动作 -->
      <div v-if="result" class="drb-done">
        <p class="drb-done__title">已重建持仓</p>
        <p>
          新建持仓 {{ reconRecordRef(result.position_id) }}，
          {{ reconQuantity(result.quantity) }}，成本均价
          {{ resultAvgPrice }} 元，来自
          {{ reconCount(result.txn_count) }} 流水。
        </p>
        <p>已可回持仓页补录这笔卖出。</p>
        <p class="drb-done__log">
          日志编号 <strong>#{{ result.log_id }}</strong>
        </p>
        <p v-if="undoSkippedNote" class="drb-done__skip">
          {{ undoSkippedNote }}
        </p>
        <el-button
          v-if="!undone && !undoSkippedNote"
          type="danger"
          plain
          :loading="undoing"
          @click="undo"
        >
          撤销此次重建
        </el-button>
        <p v-else-if="undone" class="drb-done__undone">此次重建已撤销</p>
      </div>
      <template v-else>
        <!-- 预览只给结构区（将按哪份流水建、派生出什么），不再配说明句：
             派生口径与「可凭日志编号撤销」属文档与日志（design.md「先删，再重排」②），
             后端 warnings 不整体进界面；唯一例外是「成本均价 = 0」的后果——
              它是用户点下去的那个决定的后果，括注贴在值行尾说一次。 -->
        <p v-if="previewing" class="drb-loading">正在核对流水，生成重建预览…</p>
        <template v-else-if="preview">
          <div class="drb-facts">
            <p>标的代码 {{ reconSymbolCode(preview.symbol) }}</p>
            <p>账本：{{ reconLedgerName(preview.ledger_name) }}</p>
            <p>
              {{ reconCount(preview.txn_count) }} 流水 ·
              {{ reconTradeDate(preview.first_date) }} ~
              {{ reconTradeDate(preview.last_date) }}
            </p>
            <p>
              按流水派生：净份额 {{ reconQuantity(preview.net_units) }} ·
              成本均价 {{ previewAvgPrice }} 元{{ avgPriceNote }}
            </p>
          </div>
          <p v-if="!preview.rebuildable" class="drb-block">
            {{ preview.block_reason || "这组流水暂不能重建持仓" }}
          </p>
          <el-form label-width="90px" size="default">
            <el-form-item label="原因（选填）">
              <el-input
                v-model="reason"
                placeholder="例如：旧版清仓删除了持仓行，按流水重建"
              />
            </el-form-item>
          </el-form>
        </template>
        <p v-else-if="previewError" class="drb-block">{{ previewError }}</p>
      </template>
    </div>
    <template #footer>
      <span v-if="!result && blockNote" class="drb-footer__block">{{
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
        <span class="drb-footer__submit">
          <el-button
            type="primary"
            :disabled="!canSubmit"
            :loading="submitting"
            @click="submit"
          >
            确认重建持仓
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
  previewDanglingRefRebuild,
  rebuildDanglingRefPosition,
  undoDanglingRefRebuild,
  type DanglingRefGroup,
  type DanglingRefRebuildPreview,
  type DanglingRefRebuildResult,
  type DanglingRefRebuildUndoResult
} from "@/api/reconciliation";
import { useNestedDialog } from "../composables/useNestedDialog";
import {
  reconAssetHeading,
  reconCount,
  reconLedgerName,
  reconQuantity,
  reconRecordRef,
  reconSymbolCode,
  reconTradeDate
} from "../utils/reconDisplay";

/**
 * 域 F 第三条写路径「按流水重建持仓」向导：预览（自动拉取）→ 确认写入 →
 * 凭 log_id 撤销。适用场景：持仓行被旧版「整笔卖出删行」物理删除而流水还在，
 * 「回补关联」只认现存持仓、「补全信息」只改字段，都救不了这一组。
 * 标题=名称、代码=次要事实行：主标题一律走 reconAssetHeading。
 */
const props = defineProps<{
  modelValue: boolean;
  group: DanglingRefGroup | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  rebuilt: [];
}>();

const preview = ref<DanglingRefRebuildPreview | null>(null);
const previewing = ref(false);
const previewError = ref("");
const reason = ref("");
const submitting = ref(false);
const result = ref<DanglingRefRebuildResult | null>(null);
const undoing = ref(false);
const undone = ref(false);
const undoResult = ref<DanglingRefRebuildUndoResult | null>(null);

const transactionIds = computed(() =>
  (props.group?.transactions ?? []).map(t => t.id)
);

/** 加载中回退到组本身的 symbol；有预览后用预览的名称 + 代码 */
const heading = computed(() =>
  preview.value
    ? reconAssetHeading(preview.value.symbol, preview.value.display_name)
    : reconAssetHeading(props.group?.symbol)
);

/** 价格位数走唯一真源 pricePrecision，不手写 toFixed */
const previewAvgPrice = computed(() =>
  formatPrice(preview.value?.avg_price, preview.value?.asset_type)
);
const resultAvgPrice = computed(() =>
  formatPrice(result.value?.avg_price, preview.value?.asset_type)
);

/** 成本均价为 0 的后果贴在值上说一次（后端 _rebuild_warnings 第 4 条的现场化，不渲染 warnings 列表） */
const avgPriceNote = computed(() =>
  preview.value?.avg_price === 0 ? "（组内没有买入流水，需在持仓页补成本）" : ""
);

/** 不可重建时给出可执行的下一步（后端原文），不只把按钮置灰让人猜 */
const blockNote = computed(() => {
  if (previewing.value) return "正在生成预览";
  if (previewError.value) return previewError.value;
  if (!preview.value) return "";
  if (!preview.value.rebuildable)
    return preview.value.block_reason || "这组流水暂不能重建持仓";
  return "";
});

const canSubmit = computed(
  () =>
    !!preview.value?.rebuildable &&
    !previewing.value &&
    !previewError.value &&
    transactionIds.value.length > 0
);

/** 撤销被跳过 ≠ 撤销成功：把后端原因原样亮出来，数据保持重建后的状态 */
const undoSkippedNote = computed(() => {
  if (!undoResult.value?.skipped) return "";
  return (
    undoResult.value.skip_reason ||
    "未能自动撤销：数据在重建后已被改动，本次保持现状"
  );
});

/** 抽屉内打开时登记给抽屉，避免两层遮罩叠加；不在抽屉内则静默跳过。 */
useNestedDialog(toRef(props, "modelValue"));

/** 每次打开都从干净状态开始，并立即拉预览（rebuildable=false 是正常返回） */
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
    previewError.value = "这组流水为空，无法重建";
    return;
  }
  previewing.value = true;
  try {
    const res = await previewDanglingRefRebuild(transactionIds.value);
    preview.value = res.data ?? null;
    if (!res.data) previewError.value = "预览没有返回数据";
  } catch (e) {
    previewError.value = errorMessageOf(e) || "预览失败";
  } finally {
    previewing.value = false;
  }
}

async function submit(): Promise<void> {
  // 纵深防御：后端会硬校验 confirm，前端也不许把不可重建的组提交出去
  if (!canSubmit.value || !props.group) return;
  submitting.value = true;
  try {
    const res = await rebuildDanglingRefPosition({
      transaction_ids: transactionIds.value,
      reason: reason.value || undefined,
      confirm: true
    });
    result.value = res.data ?? null;
    if (!res.data) {
      ElMessage.error("重建没有返回结果");
      return;
    }
    ElMessage.success("已重建持仓");
    emit("rebuilt");
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "重建持仓失败");
  } finally {
    submitting.value = false;
  }
}

async function undo(): Promise<void> {
  if (!result.value) return;
  undoing.value = true;
  try {
    const res = await undoDanglingRefRebuild(result.value.log_id);
    undoResult.value = res.data ?? null;
    if (res.data?.skipped) {
      ElMessage.warning(res.data.skip_reason || "未能撤销：数据期间已被改动");
      emit("rebuilt");
      return;
    }
    undone.value = true;
    ElMessage.success("此次重建已撤销");
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
.drb-loading {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.drb-facts {
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

.drb-facts p {
  margin: 0;
}

.drb-block {
  padding: 8px 10px;
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.drb-footer__block {
  margin-right: auto;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}

.drb-footer__submit {
  display: inline-flex;
  margin-left: 8px;
}

.drb-done p {
  margin: 4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.drb-done__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-success-ink);
}

.drb-done__log {
  font-variant-numeric: tabular-nums;
}

.drb-done__skip {
  padding: 6px 10px;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-sm);
}

.drb-done__undone {
  font-weight: 600;
  color: var(--color-info-ink);
}
</style>
