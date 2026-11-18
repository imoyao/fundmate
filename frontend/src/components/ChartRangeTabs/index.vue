<!--
  图表周期筛选（`#3107`）：一排常用档 + 「更多」下拉，口径见 `utils/chartRange.ts`。

  ## 为什么不是一个纯 SegmentedControl

  九档全平铺会把标题挤掉（组合详情页卡片头部已经有基准下拉），而只用下拉则让
  「近1月 / 近3月」这种高频切换多两次点击。产品图里的形态正是这个取舍：
  **4 档常驻 + 其余收进下拉**，且下拉按钮兼做「当前选中档的回显」——
  选了「近3年」时第一排全部熄灭，按钮自己变成「近3年 ▾」并高亮，
  否则用户看不出现在到底在看哪一段。

  ## 与守卫的关系（`scripts/guard_segmented.py`）

  第一排**复用 `SegmentedControl`**，不手写分段样式（守卫 RULE 3/4 会拦手写
  tablist 角色与 `-segmented` 类名）。本组件只额外长出下拉按钮这一个靶区，
  它不是分段控件（是 `el-dropdown` 的触发按钮），不构成第二套分段语言。

  ## 数据不支持时

  `keys` 允许调用方只渲染一部分档位（默认九档全给）。**当前没有调用方收窄它**：
  「哪些档画得出来」要等后端回答（作用域最早数据日 / `range_reason`），前端在
  首次请求前并不知道，猜一个只会把能画的档也藏掉。所以画不出时由调用方按
  `range_reason` 说明原因，档位本身照常可点。本组件不猜，只渲染给它的档位；
  若某档不在 `keys` 里，即使 `modelValue` 是它也不会显示为选中——那是调用方的
  状态错误，交给单测钉住。
-->
<template>
  <div class="chart-range" role="group" :aria-label="ariaLabel || '图表周期'">
    <SegmentedControl
      v-if="primaryOptions.length"
      :model-value="modelValue"
      :options="primaryOptions"
      :size="size"
      :disabled="disabled"
      :aria-label="ariaLabel ? `${ariaLabel}（常用）` : '图表周期（常用）'"
      @update:model-value="pick"
    />
    <!-- 下拉按钮：当前档在「更多」里时显示该档标签并高亮（见上方注释） -->
    <el-dropdown
      v-if="moreOptions.length"
      trigger="click"
      placement="bottom-end"
      :disabled="disabled"
      @command="pick"
    >
      <button
        type="button"
        class="chart-range__more"
        :class="{ 'is-active': isMoreValue }"
        :disabled="disabled"
        aria-haspopup="listbox"
      >
        <span>{{ moreButtonLabel }}</span>
        <IconifyIconOffline icon="ep:arrow-down" class="chart-range__caret" />
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="opt in moreOptions"
            :key="opt.value"
            :command="opt.value"
          >
            <span
              class="chart-range__item"
              :class="{ 'is-current': opt.value === modelValue }"
            >
              {{ opt.label }}
            </span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  ALL_CHART_RANGE_KEYS,
  CHART_RANGE_LABELS,
  MORE_CHART_RANGE_KEYS,
  PRIMARY_CHART_RANGE_KEYS,
  type ChartRangeKey
} from "@/utils/chartRange";

defineOptions({ name: "ChartRangeTabs" });

const props = withDefaults(
  defineProps<{
    modelValue: ChartRangeKey;
    /** 可用档位（已按数据长度过滤）；不传 = 九档全给 */
    keys?: readonly ChartRangeKey[];
    /** `small` 与卡片工具条其它控件同高（24px 轨道）；`default` 用于独立成行时 */
    size?: "default" | "small";
    disabled?: boolean;
    /** 无障碍标签：同页多组周期控件时必须区分（读屏与 E2E 定位用） */
    ariaLabel?: string;
  }>(),
  { size: "small", disabled: false, ariaLabel: "" }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: ChartRangeKey): void;
  (e: "change", value: ChartRangeKey): void;
}>();

/** 过滤后的档位：只认调用方声明为可用的，顺序仍由常量表决定（不随入参乱序） */
const available = computed(() => new Set(props.keys ?? ALL_CHART_RANGE_KEYS));

const primaryOptions = computed(() =>
  PRIMARY_CHART_RANGE_KEYS.filter(key => available.value.has(key)).map(key => ({
    label: CHART_RANGE_LABELS[key],
    value: key
  }))
);

const moreOptions = computed(() =>
  MORE_CHART_RANGE_KEYS.filter(key => available.value.has(key)).map(key => ({
    label: CHART_RANGE_LABELS[key],
    value: key
  }))
);

const isMoreValue = computed(() =>
  (MORE_CHART_RANGE_KEYS as readonly ChartRangeKey[]).includes(props.modelValue)
);

/** 未选中「更多」里任一档时按钮文案是「更多」；选中了就回显那一档 */
const moreButtonLabel = computed(() =>
  isMoreValue.value ? CHART_RANGE_LABELS[props.modelValue] : "更多"
);

function pick(value: ChartRangeKey | number | string | undefined) {
  if (!value || value === props.modelValue) return;
  const key = value as ChartRangeKey;
  emit("update:modelValue", key);
  emit("change", key);
}
</script>

<style scoped>
.chart-range {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px;
  align-items: center;
}

/* 与 SegmentedControl `small` 档同几何（20px 项高、12px 字、胶囊圆角），
   两者并排时视觉上是同一组控件而不是两个不相干的东西 */
.chart-range__more {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  height: 20px;
  padding: 0 10px;
  font-family: var(--font-ui);
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.chart-range__more:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.chart-range__more:focus {
  outline: none;
}

.chart-range__more:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

/* 选中档在「更多」里：按钮自己承担选中态（第一排全灭，否则看不出在看哪一段） */
.chart-range__more.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
}

.chart-range__more:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

.chart-range__caret {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.chart-range__item {
  display: inline-block;
  min-width: 48px;
}

.chart-range__item.is-current {
  font-weight: 600;
  color: var(--brand-700);
}
</style>
