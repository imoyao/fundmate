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
  <!-- `justify-between` 把控件分成左右两组：左边三枚「看什么」的开关（粒度 / 形态 /
       口径），右边「看哪一段」的区间导航。原先四组控件用同一个 `gap-2` 挤在一行，
       区间导航与前三个开关视觉上连成一片，用户分不清「切换维度」和「翻时间段」
       是两类不同的操作。
       窄容器下两组各自内部先折行（见下方 bp.below），而不是把导航按钮挤到开关中间。 -->
  <div class="pnl-calendar-action-bar">
    <div class="pnl-calendar-action-bar__views">
      <!-- 粒度：日 / 月 / 年。SegmentedControl 是全站唯一实现（#1717；静态守卫
           guard_segmented.py 拦截「改用 Element Plus 自带分段组件」与手写
           xxx-segmented 样式块的回潮） -->
      <SegmentedControl
        v-model="granularity"
        :options="GRANULARITY_OPTIONS"
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
    </div>

    <!-- 区间导航。`role="group"` + `aria-label` 是按钮组的正确 a11y 语义：
         组本身不是按钮，但需一个可访问名来把三枚按钮归为一组。顺带说明：守卫
         `guard_a11y_interaction.py` 的 `<(el-button|button)\b` 会把
         `el-button-group` 一并匹配上，这里给组加名是正解，不是为过守卫而塞的无用属性。

         年视图没有导航：它的区间恒为「投资以来 → 今年」，往前翻只会有建仓前的空年份、
         往后翻本来就是空的。给一组按不动的按钮是骗人的，故只留一个区间标签。 -->
    <div v-if="granularity !== 'year'" class="pnl-calendar-action-bar__nav">
      <el-button-group role="group" :aria-label="nav.groupAria">
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
    </div>
    <span v-else class="pnl-calendar-action-bar__range">{{ rangeLabel }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { VALUE_MODE_OPTIONS, type PnlCalendarValueMode } from "./helpers";
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
}>();

const emit = defineEmits<{
  (e: "shift", delta: number): void;
  (e: "goCurrent"): void;
}>();

const GRANULARITY_OPTIONS = [
  { label: "日收益", value: "day" },
  { label: "月收益", value: "month" },
  { label: "年收益", value: "year" }
] as const;

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

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 两组控件之间靠 `justify-content: space-between` 拉开（见模板注释）：
   窄容器里两组会各自成行，此时 space-between 退化为左对齐一列，
   不会把区间导航推到与开关组错位的一侧。 */
.pnl-calendar-action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  justify-content: space-between;
}

/* 左组：三枚开关之间用小 gap（8px），它们同属「切换看什么」，靠得近些 */
.pnl-calendar-action-bar__views {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* 右组：区间导航与当前区间标签。窄屏时它换行到左组下方并左对齐——
   若继续 justify-end 会被推到最右，与上方左组拉开一条无意义的空白。 */
.pnl-calendar-action-bar__nav {
  display: flex;
  align-items: center;
}

/* 年视图的区间标签（替代区间导航按钮组：年视图区间固定，按不动的按钮是骗人的） */
.pnl-calendar-action-bar__range {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 窄屏（半宽容器 / 账户详情）两组纵向堆叠。断点走 _breakpoints.scss 单一来源
   （`bp.below("sm")` = < 640px），禁手写像素——guard_breakpoints.py 会拦。
   注意这两条覆盖必须排在基础声明**之后**：媒体查询不改变特异性，写在前面会被压掉。 */
@include bp.below("sm") {
  .pnl-calendar-action-bar {
    justify-content: flex-start;
  }

  .pnl-calendar-action-bar__views {
    width: 100%;
  }
}
</style>
