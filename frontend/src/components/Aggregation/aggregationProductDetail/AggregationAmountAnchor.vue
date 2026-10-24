<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { AggregationProductGroup } from "@/api/ledger";
import { allocateValue } from "@/api/positions";
import {
  buildAllocationPreview,
  canAllocate,
  cashFlowHintOf,
  previewSumYuan,
  sourceWeightCents,
  yuanFromCents
} from "./aggregationDetailModel";

/**
 * 大数字锚点区（#1176）：可就地改产品总价，并按各账户既有市值占比分摊。
 *
 * 多根片段（`.amount-anchor` + `.cash-flow-hint`）：两者在父层本是并列兄弟，
 * 包一层 wrapper 会多出一个 DOM 层级，而资金进出提示的 `margin-top` 与
 * `.amount-anchor` 的 `border-bottom` 是相邻关系，多一层会改变盒模型。
 */
defineOptions({ name: "AggregationAmountAnchor" });

const props = withDefaults(
  defineProps<{
    /** 产品聚合数据 */
    group?: AggregationProductGroup | null;
    /** 抽屉是否可见（关闭时复位编辑态，避免下次打开残留上次输入） */
    visible?: boolean;
  }>(),
  {
    group: null,
    visible: false
  }
);

const emit = defineEmits<{
  /** 分摊保存成功；调用方需刷新聚合数据（#1176） */
  (e: "saved"): void;
}>();

/** 汇总市值（元） */
const totalYuan = computed(() =>
  yuanFromCents(props.group?.market_value_cents)
);
/** 来源列表（分摊的分子与分母都来自这里） */
const sources = computed(() => props.group?.sources ?? []);

// ── 产品维度改总价 + 按占比分摊（#1176）──
/** 是否处于编辑态 */
const editing = ref(false);
/** 编辑中的产品总价（元） */
const inputTotal = ref<number | null>(null);
/** 保存中 */
const saving = ref(false);
/** 资金进出提示（#1217） */
const cashFlowHint = ref<string | null>(null);

/** 有来源持仓才允许改总价 */
const canEdit = computed(() => canAllocate(sources.value));
/** 分摊分母：各账户既有市值合计（分） */
const totalWeightCents = computed(() => sourceWeightCents(sources.value));
/** 分摊预览（与后端同算法） */
const previewRows = computed(() =>
  buildAllocationPreview(sources.value, inputTotal.value)
);
/** 预览合计（元），恒等于输入总价 */
const previewSum = computed(() => previewSumYuan(previewRows.value));

// 抽屉关闭时复位编辑态，避免下次打开残留上次的输入
watch(
  () => props.visible,
  visible => {
    if (!visible) {
      editing.value = false;
      inputTotal.value = null;
      cashFlowHint.value = null;
    }
  }
);

function startEdit() {
  inputTotal.value = Number(totalYuan.value.toFixed(2));
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  inputTotal.value = null;
  cashFlowHint.value = null;
}

async function save() {
  const total = Number(inputTotal.value);
  if (!props.group?.symbol) return;
  if (!Number.isFinite(total) || total <= 0) {
    ElMessage.warning("请输入大于 0 的产品总价");
    return;
  }
  if (totalWeightCents.value <= 0) {
    ElMessage.warning("当前各账户市值均为 0，无法按比例分摊，请先录入市值");
    return;
  }

  saving.value = true;
  try {
    const res = await allocateValue({
      symbol: props.group.symbol,
      total_value: total
    });
    cashFlowHint.value = cashFlowHintOf(res?.data);
    ElMessage.success("总价已按占比分摊到各账户");
    editing.value = false;
    emit("saved");
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || "分摊失败，请稍后重试");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <!-- 大数字锚点（#1176：可就地改产品总价并按占比分摊） -->
  <div class="amount-anchor">
    <div class="amount-head">
      <el-tooltip
        placement="top-start"
        content="资产情况为当前持有份额 × 最新参考净值"
      >
        <div class="amount-label">资产情况(元)</div>
      </el-tooltip>
      <el-button
        v-if="!editing && canEdit"
        link
        type="primary"
        class="edit-btn"
        @click="startEdit"
      >
        更新总价
      </el-button>
    </div>

    <!-- 只读态 -->
    <MoneyDisplay
      v-if="!editing"
      :value="totalYuan"
      size="xl"
      :show-sign="false"
      :auto-color="false"
    />

    <!-- 编辑态：改总价 → 按各账户既有市值占比实时预览 → 保存落库 -->
    <template v-else>
      <el-input-number
        v-model="inputTotal"
        class="total-input"
        :min="0.01"
        :precision="2"
        :step="100"
        :controls="false"
        placeholder="请输入产品总价"
      />
      <p class="edit-hint">
        修改后将按各账户<strong>当前市值占比</strong>自动分摊（整数分，尾差归占比最大的一笔）
      </p>

      <div v-if="previewRows.length" class="preview-block">
        <div class="preview-head">
          <span class="preview-title">分摊预览</span>
          <span class="preview-sum">
            合计
            <MoneyDisplay
              :value="previewSum"
              size="sm"
              :show-sign="false"
              :auto-color="false"
            />
          </span>
        </div>
        <div v-for="row in previewRows" :key="row.key" class="preview-row">
          <span class="preview-name" :title="row.name">{{ row.name }}</span>
          <span class="preview-ratio">{{ row.ratioText }}</span>
          <MoneyDisplay
            :value="row.allocatedYuan"
            size="sm"
            :show-sign="false"
            :auto-color="false"
          />
        </div>
      </div>

      <div class="edit-actions">
        <el-button type="primary" :loading="saving" @click="save">
          保存
        </el-button>
        <el-button :disabled="saving" @click="cancelEdit">取消</el-button>
      </div>
    </template>
  </div>

  <!-- 资金进出提示（#1217）：来自后端的「下一开盘日」建议 -->
  <div v-if="cashFlowHint" class="cash-flow-hint">
    <IconifyIconOffline icon="ep:warning-filled" class="hint-icon" />
    <span class="hint-text">{{ cashFlowHint }}</span>
  </div>
</template>

<style scoped>
/* ── 大数字锚点 ── */
.amount-anchor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: var(--space-5, 24px);
  border-bottom: 1px solid var(--border-light);
}

/* 标签与「更新总价」入口同一行，右侧对齐 */
.amount-head {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.amount-label {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.edit-btn {
  flex: none;
  padding: 0;
  font-size: var(--text-label);
}

/* ── 编辑态：改总价 + 分摊预览（#1176）── */
.total-input {
  width: 100%;
  margin-top: 4px;
}

.edit-hint {
  margin: 8px 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.preview-block {
  padding: var(--space-3, 12px);
  margin-top: var(--space-3, 12px);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.preview-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.preview-title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.preview-sum {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.preview-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  padding: 4px 0;
  font-size: var(--text-label);
}

.preview-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  white-space: nowrap;
}

.preview-ratio {
  flex: none;
  font-family: var(--font-mono);
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.edit-actions {
  display: flex;
  gap: 8px;
  margin-top: var(--space-compact);
}

/* ── 资金进出提示（#1217）── */
.cash-flow-hint {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: var(--space-3, 12px);
  margin-top: var(--space-compact);
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.hint-icon {
  flex: none;
  margin-top: 2px;
  font-size: var(--text-label);
  color: var(--brand-500, #f69988);
}

.hint-text {
  min-width: 0;
  word-break: break-word;
}
</style>
