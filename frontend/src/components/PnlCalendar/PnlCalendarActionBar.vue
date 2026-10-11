<!--
  PnlCalendarActionBar · 收益日历控件排（粒度 / 形态 / 口径 / 区间导航）

  从 PnlCalendar/index.vue 的 `#action` 插槽抽出（#2050）：`hostHeader` 模式下
  PnlCalendar 不再渲染 SectionHeader，控件排需要独立渲染。抽出后两种模式共用
  同一份标记与绑定，避免两处各写一份出现漂移。

  ## v-model

  - `granularity`：日 / 月 / 年
  - `view`：日历图（方格图）/ 柱状图
  - `valueMode`：金额 / 收益率

  三个都是 PnlCalendar 的内部状态，用 `defineModel` 双向绑定，调用方无需手动
  传 `@update:*` 事件。
-->

<template>
  <div class="flex flex-wrap items-center justify-end gap-2">
    <!-- 粒度：日 / 月 / 年。SegmentedControl 是全站唯一实现（#1717；静态守卫
         guard_segmented.py 拦截「改用 Element Plus 自带分段组件」与手写
         xxx-segmented 样式块的回潮）。
         选项随宿主的 `granularities` 过滤（#2033）：本卡只给两档时这里就只列两档，
         排序始终按 ALL_GRANULARITIES 的固定顺序，不跟宿主传入的数组顺序走。 -->
    <SegmentedControl
      v-model="granularity"
      :options="granularityChoices"
      size="small"
      ariaLabel="切换收益粒度"
    />
    <!-- 形态：日 / 月 / 年三粒度**都有**两种呈现角度（#1942）。
         标签随粒度变化（日历图 / 方格图），因为「一屏一个月」与
         「12 个月各一格」是两种不同的看图方式，不该共用一个词。 -->
    <SegmentedControl
      v-model="view"
      :options="viewOptions"
      size="small"
      ariaLabel="切换呈现形态"
    />
    <!-- 口径：金额 / 收益率（#1942 第二轮②）。三视图共用同一个开关，
         切换**不重新请求**——`rate` 随每次响应一并下发，前端只换显示口径。
         合计行不跟随它：金额与收益率同时显示（一个数不该因为开关而消失）。 -->
    <SegmentedControl
      v-model="valueMode"
      :options="VALUE_MODE_OPTIONS"
      size="small"
      ariaLabel="切换金额或收益率"
    />
    <!-- 区间导航。`role="group"` + `aria-label` 是按钮组的正确 a11y 语义：
         组本身不是按钮，但需一个可访问名来把三枚按钮归为一组。顺带说明：守卫
         `guard_a11y_interaction.py` 的 `<(el-button|button)\b` 会把
         `el-button-group` 一并匹配上，这里给组加名是正解，不是为过守卫而塞的无用属性。

         年视图没有导航：它的区间恒为「投资以来 → 今年」，往前翻只会有建仓前的空年份、
         往后翻本来就是空的。给一组按不动的按钮是骗人的，故只留一个区间标签。 -->
    <el-button-group
      v-if="granularity !== 'year'"
      role="group"
      :aria-label="nav.groupAria"
    >
      <el-button
        size="small"
        text
        :aria-label="nav.prev"
        :disabled="loading"
        @click="emit('shift', -1)"
      >
        <IconifyIconOffline icon="ep:arrow-left" />
      </el-button>
      <el-button
        size="small"
        text
        :disabled="loading"
        @click="emit('goCurrent')"
      >
        {{ rangeLabel }}
      </el-button>
      <el-button
        size="small"
        text
        :aria-label="nav.next"
        :disabled="loading"
        @click="emit('shift', 1)"
      >
        <IconifyIconOffline icon="ep:arrow-right" />
      </el-button>
    </el-button-group>
    <span v-else class="pnl-calendar-action-bar__range">{{ rangeLabel }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  ALL_GRANULARITIES,
  granularityOptions,
  VALUE_MODE_OPTIONS,
  type PnlCalendarValueMode
} from "./helpers";
import type { PnlCalendarGranularity } from "@/api/summary";

defineOptions({ name: "PnlCalendarActionBar" });

const granularity = defineModel<PnlCalendarGranularity>("granularity", {
  required: true
});
const view = defineModel<"calendar" | "bar">("view", { required: true });
const valueMode = defineModel<PnlCalendarValueMode>("valueMode", {
  required: true
});

const props = defineProps<{
  loading: boolean;
  rangeLabel: string;
  /**
   * 宿主允许的粒度档位（#2033）；不传 = 三档全开（welcome / 账户详情）。
   *
   * 之前这里是一份写死的三档常量，改成受 prop 约束：等高兄弟容器（如资产总览右卡，
   * 卡片体锁死 280px）根本放不下日粒度，而下钻链最后一级正是日粒度——
   * 只挡控件不挡点击会留下「控件里没有日、点一下却掉进日日历」的漏洞，
   * 那一侧的挡由 PnlCalendar 的 `selectPeriod` 一起做（见 helpers.nextGranularity）。
   */
  granularities?: readonly PnlCalendarGranularity[];
}>();

const emit = defineEmits<{
  (e: "shift", delta: number): void;
  (e: "goCurrent"): void;
}>();

/** 粒度选项 = 全站三档里宿主允许的那几档（空数组视作不约束，保持三档） */
const granularityChoices = computed(() =>
  granularityOptions(
    props.granularities?.length ? props.granularities : ALL_GRANULARITIES
  )
);

/**
 * 形态选项随粒度改名：日粒度是**日历**（一屏一个月，看「哪几天」），
 * 月 / 年粒度是**方格**（一格一个期间，看「哪些期间」）。三者共用一套 `view` 取值，
 * 切粒度时不清空（切回来还是你上次选的形态）。
 */
const viewOptions = computed(() =>
  granularity.value === "day"
    ? [
        { label: "日历图", value: "calendar" },
        { label: "柱状图", value: "bar" }
      ]
    : [
        { label: "方格图", value: "calendar" },
        { label: "柱状图", value: "bar" }
      ]
);

/** 导航语义随粒度切换：日=按月翻，月=按年翻（年视图无导航，见模板） */
const nav = computed(() => {
  const isDay = granularity.value === "day";
  return {
    groupAria: isDay ? "月份导航" : "年份导航",
    prev: isDay ? "上个月" : "上一年",
    next: isDay ? "下个月" : "下一年"
  };
});

// 消除 props 未使用告警（loading / rangeLabel 在模板中使用）
void props;
</script>

<style scoped>
/* 年视图的区间标签（替代区间导航按钮组：年视图区间固定，按不动的按钮是骗人的） */
.pnl-calendar-action-bar__range {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
