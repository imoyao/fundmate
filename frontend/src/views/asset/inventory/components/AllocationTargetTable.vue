<template>
  <div class="allocation-card__rows">
    <div
      class="allocation-card__row allocation-card__row--head"
      :class="{ 'allocation-card__row--readonly': !editing }"
    >
      <span class="allocation-card__cell">标的</span>
      <span class="allocation-card__cell allocation-card__cell--num">当前</span>
      <span class="allocation-card__cell allocation-card__cell--num">目标</span>
      <span class="allocation-card__cell allocation-card__cell--num">偏离</span>
      <span v-if="editing" class="allocation-card__cell--op" />
    </div>

    <div
      v-for="(row, index) in visibleRows"
      :key="row.symbol"
      class="allocation-card__row"
      :class="{
        'allocation-card__row--breached': row.breached,
        'allocation-card__row--readonly': !editing
      }"
    >
      <span class="allocation-card__cell allocation-card__name">
        <span class="allocation-card__title">{{ row.name }}</span>
        <span class="allocation-card__symbol">{{ row.symbol }}</span>
      </span>

      <span class="allocation-card__cell allocation-card__cell--num">
        {{ formatPct(row.weight_pct) }}%
      </span>

      <!-- 编辑态：数字输入（0~100，步长 0.5）；留空 = 不设目标。
           必须绑 `rows[index]` 而不是 computed 里的 `row`——后者是每次重算
           产出的新对象，写进去不会落回数据源，输入框会「打完字就跳回原值」。 -->
      <span v-if="editing" class="allocation-card__cell--input">
        <el-input-number
          :model-value="row.target"
          size="small"
          :min="0"
          :max="100"
          :step="0.5"
          :precision="2"
          :aria-label="`${row.name} 的目标占比`"
          controls-position="right"
          @update:model-value="emit('update-target', index, $event)"
        />
      </span>
      <span
        v-else
        class="allocation-card__cell allocation-card__cell--num"
        :class="{ 'allocation-card__cell--muted': row.target_pct === null }"
      >
        {{ row.target_pct === null ? "未设" : formatPct(row.target_pct) + "%" }}
      </span>

      <span
        class="allocation-card__cell allocation-card__cell--num"
        :class="{
          'allocation-card__cell--breached': row.breached,
          'allocation-card__cell--muted': row.deviation_pct === null
        }"
      >
        {{
          row.deviation_pct === null ? "—" : signedPct(row.deviation_pct) + "%"
        }}
      </span>

      <span v-if="editing" class="allocation-card__cell--op">
        <el-button
          text
          size="small"
          :aria-label="`移除 ${row.name}`"
          @click="emit('remove', row.symbol)"
          >移除</el-button
        >
      </span>
    </div>
  </div>

  <!-- 编辑态：把移除掉的标的加回来（只能选当前持仓，不能凭空造 code） -->
  <div v-if="editing" class="allocation-card__add">
    <el-select
      :model-value="pendingSymbol"
      size="small"
      placeholder="添加标的"
      :disabled="addableSymbols.length === 0"
      aria-label="添加标的"
      @update:model-value="emit('update:pendingSymbol', $event)"
    >
      <el-option
        v-for="opt in addableSymbols"
        :key="opt.symbol"
        :label="opt.name"
        :value="opt.symbol"
      />
    </el-select>
    <el-button size="small" :disabled="!pendingSymbol" @click="emit('add')"
      >添加</el-button
    >
  </div>

  <p class="allocation-card__footnote">
    当前 {{ data?.configured_count ?? 0 }} 个标的设有目标，其中
    {{ data?.breached_count ?? 0 }} 个偏离达到阈值
    {{ formatPct(data?.threshold_pct) }} 个百分点。
  </p>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { AllocationData } from "@/api/strategyEngine";
import {
  buildAddableSymbols,
  buildVisibleRows,
  formatPct,
  signedPct,
  type EditRow
} from "./allocationTargetModel";

/**
 * 目标配比的表格区（#980 拆分自 `AllocationTargetCard.vue`）。
 *
 * 行头、数据行、编辑态的操作列与底部脚注原先占该文件模板的 2/3、样式的 1/2。
 * 组件不持有编辑行状态：`rows` 与 `pendingSymbol` 都来自父级，
 * 输入用 `update-target` 回抛，因此「编辑中的临时值」仍只有一份来源。
 */
defineOptions({ name: "AllocationTargetTable" });

const props = withDefaults(
  defineProps<{
    data?: AllocationData | null;
    editing?: boolean;
    rows?: EditRow[];
    /** 待添加的标的代码（编辑态 select 的当前值） */
    pendingSymbol?: string;
  }>(),
  { data: null, editing: false, rows: () => [], pendingSymbol: "" }
);

const emit = defineEmits<{
  "update-target": [index: number, value: number | null | undefined];
  "update:pendingSymbol": [value: string];
  remove: [symbol: string];
  add: [];
}>();

const visibleRows = computed(() =>
  buildVisibleRows(props.data ?? null, props.editing, props.rows)
);

const addableSymbols = computed(() =>
  buildAddableSymbols(props.data ?? null, props.rows)
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.allocation-card__rows {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  overflow-y: auto;
}

.allocation-card__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px 72px 80px 56px;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-2) var(--space-2);
  border-bottom: 1px solid var(--border-light);
  border-radius: var(--radius-sm);

  /* 窄屏：压缩数字列宽，让标的名占满剩余空间。
     放在 .allocation-card__row--readonly 之前是有意的级联顺序：同特异性下源序即优先级，
     只读态的窄屏列宽在 --readonly 内再压一档，见下方注释。 */
  @include bp.below("md") {
    grid-template-columns: minmax(0, 1fr) 64px 64px 72px 48px;
    gap: var(--space-1);
  }

  /* 越线：整行给一层暖沙金底纹——它是「你定的线被越过了」，
     用告警色而非涨跌色，避免被读成「亏了」 */
  &--breached {
    background: var(--color-warning-20);
  }

  &--head {
    padding-top: 0;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
    border-bottom-color: var(--border-default);
  }

  /* 只读态没有「移除」列：收掉列宽，否则行尾空出 56px */
  &--readonly {
    grid-template-columns: minmax(0, 1fr) 72px 72px 80px;

    @include bp.below("md") {
      grid-template-columns: minmax(0, 1fr) 64px 64px 72px;
    }
  }
}

.allocation-card__cell {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;

  &--num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  &--muted {
    color: var(--text-tertiary-ink);
  }

  /* 偏离值越线：文字级告警色（底色级令牌作正文不足 4.5:1） */
  &--breached {
    font-weight: 600;
    color: var(--color-warning-ink);
  }

  &--op {
    text-align: right;
  }
}

.allocation-card__name {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.allocation-card__title {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.allocation-card__symbol {
  font-family: var(--font-mono);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.allocation-card__add {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-3);
}

.allocation-card__footnote {
  margin: 0;
  margin-top: var(--space-3);
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
