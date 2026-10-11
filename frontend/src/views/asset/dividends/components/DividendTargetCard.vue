<!--
  DividendTargetCard · 股息目标设置与达成度（#872）

  目标由用户设定（家庭级一条），达成度由 `GET /api/dividends/summary/` 随总览一起返回——
  本组件只做「展示 + 写回」，不自行计算实际股息率（口径唯一出口在后端 dividend_service）。
-->
<template>
  <CardBlock>
    <SectionHeader
      title="股息目标"
      info="设定期望的年化股息率，用于对照组合实际的「分红 / 成本」回报"
    >
      <template #action>
        <el-button
          v-if="target.configured && !editing"
          text
          size="small"
          @click="startEdit"
        >
          编辑
        </el-button>
      </template>
    </SectionHeader>

    <!-- 未设置：直接给输入入口 -->
    <div v-if="!target.configured || editing" class="target-editor">
      <div class="target-editor__row">
        <span class="target-editor__label">目标年化股息率</span>
        <el-input-number
          v-model="draft"
          :min="0.01"
          :max="100"
          :step="0.5"
          :precision="2"
          :controls="false"
          class="target-editor__input"
          aria-label="目标年化股息率（%）"
        />
        <span class="target-editor__unit">%</span>
      </div>
      <p class="target-editor__hint">
        分子为「近 {{ months }} 个月现金分红 + 红利再投资 −
        红利税」，分母为当前持仓成本。
      </p>
      <div class="target-editor__actions">
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!draft || draft <= 0"
          @click="onSave"
        >
          保存目标
        </el-button>
        <el-button v-if="editing" text @click="cancelEdit">取消</el-button>
      </div>
    </div>

    <!-- 已设置：目标 + 达成度 -->
    <div v-else class="target-view">
      <div class="target-view__nums">
        <div class="target-view__item">
          <span class="target-view__label">目标股息率</span>
          <span class="target-view__value">
            {{ target.target_yield_pct?.toFixed(2) }}<small>%</small>
          </span>
        </div>
        <div class="target-view__item">
          <span class="target-view__label">实际股息率</span>
          <span class="target-view__value target-view__value--actual">
            <template v-if="actualPct !== null">
              {{ actualPct.toFixed(2) }}<small>%</small>
            </template>
            <template v-else>--</template>
          </span>
        </div>
        <div class="target-view__item">
          <span class="target-view__label">达成度</span>
          <span class="target-view__value">
            <template v-if="target.progress_pct !== null">
              {{ target.progress_pct.toFixed(1) }}<small>%</small>
            </template>
            <template v-else>--</template>
          </span>
        </div>
      </div>

      <el-progress
        class="target-view__bar"
        :percentage="barPercent"
        :show-text="false"
        :stroke-width="8"
      />

      <p class="target-view__status">
        <span class="target-view__tag" :class="tagClass">
          {{ statusLabel }}
        </span>
        <span v-if="gapText" class="target-view__gap">{{ gapText }}</span>
        <span v-if="target.notes" class="target-view__notes">
          · {{ target.notes }}
        </span>
      </p>

      <el-button text size="small" type="danger" @click="onClear">
        清除目标
      </el-button>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  clearDividendTarget,
  saveDividendTarget,
  type DividendTarget
} from "@/api/dividends";

const props = defineProps<{
  target: DividendTarget;
  /** 组合实际股息率（成本口径，%）；无持仓成本时为 null */
  actualPct: number | null;
  /** 统计窗口月数，仅用于文案 */
  months: number;
}>();

const emit = defineEmits<{ saved: [] }>();

const editing = ref(false);
const saving = ref(false);
const draft = ref<number | null>(null);

watch(
  () => props.target.target_yield_pct,
  value => {
    draft.value = value;
  },
  { immediate: true }
);

/** 进度条百分比固定 0~100（真实达成度以文字呈现，避免进度条溢出变形） */
const barPercent = computed(() =>
  Math.min(100, Math.max(0, props.target.progress_pct ?? 0))
);

const statusLabel = computed(() => {
  if (props.target.met === null) return "待补充数据";
  return props.target.met ? "已达标" : "未达标";
});

const tagClass = computed(() => {
  if (props.target.met === null) return "target-view__tag--muted";
  return props.target.met
    ? "target-view__tag--reached"
    : "target-view__tag--pending";
});

const gapText = computed(() => {
  const gap = props.target.gap_pct;
  if (gap === null || gap === undefined) return "";
  const sign = gap > 0 ? "+" : "";
  return `较目标 ${sign}${gap.toFixed(2)} 个百分点`;
});

function startEdit() {
  draft.value = props.target.target_yield_pct;
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  draft.value = props.target.target_yield_pct;
}

async function onSave() {
  const value = draft.value;
  if (!value || value <= 0) return;
  saving.value = true;
  try {
    await saveDividendTarget({
      target_yield_pct: value,
      notes: props.target.notes
    });
    editing.value = false;
    ElMessage.success("股息目标已保存");
    emit("saved");
  } catch {
    // 错误提示由 http 拦截器统一给出，这里只保证不静默改变本地状态
  } finally {
    saving.value = false;
  }
}

async function onClear() {
  try {
    await clearDividendTarget();
    editing.value = false;
    ElMessage.success("股息目标已清除");
    emit("saved");
  } catch {
    /* 同上 */
  }
}
</script>

<style lang="scss" scoped>
.target-editor__row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.target-editor__label {
  font-size: 13px;
  color: var(--text-secondary);
}

.target-editor__input {
  width: 120px;
}

.target-editor__unit {
  font-size: 14px;
  color: var(--text-tertiary);
}

.target-editor__hint {
  margin-top: var(--space-2);
  font-size: 12px;
  color: var(--text-tertiary);
}

.target-editor__actions {
  margin-top: var(--space-3);
}

.target-view__nums {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
}

.target-view__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.target-view__label {
  font-size: 13px;
  color: var(--text-secondary);
}

.target-view__value {
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);

  small {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-tertiary);
  }

  &--actual {
    color: var(--brand-700);
  }
}

.target-view__bar {
  margin-top: var(--space-3);

  :deep(.el-progress-bar__inner) {
    background-color: var(--brand-700);
  }
}

.target-view__status {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
  font-size: 12px;
  color: var(--text-tertiary);
}

.target-view__tag {
  padding: 1px 8px;
  font-size: 12px;
  border-radius: var(--radius-pill);

  &--reached {
    color: var(--brand-700);
    background: var(--brand-100);
  }

  &--pending {
    color: var(--text-secondary);
    background: var(--bg-soft);
  }

  &--muted {
    color: var(--text-tertiary);
    background: var(--bg-muted);
  }
}

.target-view__notes {
  color: var(--text-tertiary);
}
</style>
