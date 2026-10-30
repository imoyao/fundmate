<script setup lang="ts">
import { computed } from "vue";
import { ArrowDown } from "@element-plus/icons-vue";
import type { DayPnlMetric } from "@/views/asset/watchlist/dayPnl";

/**
 * 「当日盈亏」列头（2026-10-30）：列名 + 排序口径下拉。
 *
 * ## 为什么需要它
 *
 * 这一列是**复合列**：金额（主行）+ 当日涨跌幅（副行），两行是两个不同的量。
 * 用户有时想「今天谁赚得最多」（按金额），有时想「今天谁涨得最凶」（按涨幅）——
 * #2641 把排序代理到 `change_pct` 之后，「按金额排序」在实现上根本不存在，
 * 用户点名要的是同花顺那种「切换指标再排序」。
 *
 * ## 为什么是列头里的小箭头而不是表头上方一排按钮
 *
 * 口径是**这一列**的属性，不是整张表的属性；放到表头上方会让人以为是全局开关。
 * 列宽只有 104px（默认列预算 1040 已用满 1036），所以按钮做成 12px 的箭头图标，
 * 语义交给 tooltip 与下拉菜单文案——不再挤占固定预算（见 columnDefs 铁律 1）。
 *
 * 点击箭头不触发排序（`@click.stop`），排序仍由点列名本体触发；选择口径后由
 * 父组件按该口径重排一次（同花顺式：切完指标就给结果）。
 */
const props = defineProps<{ metric: DayPnlMetric }>();

const emit = defineEmits<{
  (e: "change", metric: DayPnlMetric): void;
}>();

const currentLabel = computed(() =>
  props.metric === "amount" ? "金额" : "涨幅"
);
const hint = computed(
  () => `排序口径：${currentLabel.value}（点箭头切换金额 / 涨幅）`
);

function onCommand(command: string | number | object) {
  const next: DayPnlMetric = command === "pct" ? "pct" : "amount";
  if (next === props.metric) return;
  emit("change", next);
}
</script>

<template>
  <span class="dp-header">
    <span class="dp-header__label">当日盈亏</span>
    <!-- 不用 el-tooltip 包 el-dropdown：两层 popper 叠在 th 里，tooltip 的悬浮层会
         干扰下拉的展开/点击（表头本身还在 EP 的 click 排序监听之下）。原生 title
         的提示效果足够，且零层级风险。 -->
    <el-dropdown trigger="click" @command="onCommand" @click.stop>
      <el-icon class="dp-header__more" :title="hint" @click.stop>
        <ArrowDown />
      </el-icon>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            command="amount"
            :class="{ 'is-active': metric === 'amount' }"
          >
            按金额排序
          </el-dropdown-item>
          <el-dropdown-item
            command="pct"
            :class="{ 'is-active': metric === 'pct' }"
          >
            按涨幅排序
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </span>
</template>

<style scoped>
.dp-header {
  display: inline-flex;
  gap: 2px;
  align-items: center;
}

/* 12px：表头可用宽度只够一个「第二行数字口径」的提示点，不做成按钮样式，
   但保留 20×20 的点击热区（用 padding 扩展，不占布局宽度） */
.dp-header__more {
  width: 12px;
  height: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  outline: none;
}

.dp-header__more:hover {
  color: var(--brand-ink);
}

.dp-header__more:focus-visible {
  outline: 2px solid var(--brand-ink);
  outline-offset: 2px;
}

:deep(.is-active) {
  font-weight: 600;
  color: var(--brand-ink);
}
</style>
