<!--
  行业分布区（#2617；2026-10-30 改口径命名 + 持仓结构改环形图）。

  两档口径：
  - **持仓结构**（原「直接持有」）：基金整块显示为「基金」，不拆底层。回答
    「我自己直接买了什么」。
  - **穿透持仓**（原「穿透后」）：基金按底层持仓并入行业。回答「我的钱最终押在
    哪些行业」。

  为什么必须在同一个区块里放切换而不是两张图并排：两档的分母与量级都不同，并排会
  诱导读者把两个图的数字相加（会得出「基金是制造业」这类假结论）。

  为什么两档用**不同的呈现**（2026-10-30 owner 要求）：
  - 持仓结构是「我买了哪几块」的**构成**问题 —— 环形图一眼看清「基金占大头还是
    现金占大头」，这正是构成图擅长的事；
  - 穿透持仓是「押在哪些行业」的**排序**问题 —— 门类多（证监会 19 个），条形列表
    能一屏排完并保持可比长度，换饼图反而要靠肉眼比角度。

  为什么这是子组件：`PenetrationPanel` 触到 `check_vue_size` 的 400 行阈值
  （issue #980），本区块的模板 + 两个口径的行构造逻辑独立于其余部分。
-->
<template>
  <div>
    <div class="panel-head">
      <h4 class="panel-subtitle">行业分布</h4>
      <SegmentedControl
        v-model="view"
        :options="VIEW_OPTIONS"
        size="small"
        aria-label="行业视图"
      />
    </div>
    <p class="panel-view-hint">{{ viewHint }}</p>
    <!-- 诚实降级：主口径没有「个股→行业」映射时结构图必然缺一块，
         把后端给的成因原样透出，避免用户把缺口读成计算缺陷 -->
    <SoftBanner
      v-if="mappingHint"
      class="mb-2"
      variant="info"
      icon="ep:info-filled"
    >
      {{ mappingHint }}
    </SoftBanner>

    <!-- 穿透持仓：条形列表（19 个门类一屏排完，条形长度可直接横向比较） -->
    <template v-if="view === 'penetrated'">
      <p
        v-if="!penetratedRows.length"
        class="text-sm"
        :style="{ color: 'var(--text-secondary)' }"
      >
        暂无可用的行业配置数据。
      </p>
      <PenetrationBarList v-else :rows="penetratedRows" />
    </template>

    <!-- 持仓结构：环形图（构成问题用构成图，中心不写字、图例带占比） -->
    <AssetAllocationDonut
      v-else
      :data="structureData"
      :color-map="STRUCTURE_COLORS"
      empty-text="暂无持仓结构数据"
      :legend-font-size="10"
      class="structure-donut"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import PenetrationBarList from "./PenetrationBarList.vue";
import { barWidth, percent } from "./format";
import type { PenetrationData } from "@/api/summary";

const props = defineProps<{ data: PenetrationData }>();

/** 两档视图：持仓结构（基金整块）/ 穿透持仓（基金并入行业）。
 *  默认穿透持仓 = 既有行为，不改变旧用户的阅读习惯。 */
const VIEW_OPTIONS = [
  { label: "持仓结构", value: "direct" },
  { label: "穿透持仓", value: "penetrated" }
] as const;

const view = ref<"direct" | "penetrated">("penetrated");

/** 行业行：条形以「已穿透」为分母，右侧数值仍按总市值占比（两个分母不同，别混） */
const penetratedRows = computed(() =>
  props.data.industries.map(row => ({
    key: row.code,
    name: row.name,
    title: `${row.name}（${row.code}）· ${row.fund_count} 只基金持有`,
    width: barWidth(row.ratio_of_penetrated),
    value: percent(row.ratio_of_total)
  }))
);

/**
 * 持仓结构（#2617 原「直接持有」口径）的环形图数据：
 * 直持行业 + 基金整块 + 未映射直持 + 现金等价物，各项合计 = 持仓总市值。
 *
 * 数值一律取后端的 `*_cny`（元），**不在前端做除法**——占比由环形图组件按
 * 各扇区之和实时算，与「穿透持仓」条形图各算各的口径互不影响。
 */
const STRUCTURE_COLORS: Record<string, string> = {
  "基金（未拆底层）": "--chart-07",
  未映射直持: "--chart-08",
  现金等价物: "--chart-05",
  其他行业: "--chart-03"
};

/**
 * 扇区上限：直持行业超过 8 个时把尾部折成「其他行业」。
 *
 * 为什么不全部铺开：图例在底部绝对定位、换行不挤压圆环，条目一多就压住扇区
 * （见 `AssetAllocationDonut` 的 radius/center 注释）。环形图只回答「结构」，
 * 完整明细由「穿透持仓」的条形列表承担——两档本来就分工不同。
 */
const MAX_SLICES = 8;

const structureData = computed(() => {
  const dv = props.data.direct_view;
  const industries = dv.industries.map(row => ({
    name: row.name,
    value: row.value_cny
  }));
  const rows =
    industries.length > MAX_SLICES
      ? (() => {
          const head = industries.slice(0, MAX_SLICES);
          const rest = industries
            .slice(MAX_SLICES)
            .reduce((sum, row) => sum + row.value, 0);
          if (rest > 0) head.push({ name: "其他行业", value: rest });
          return head;
        })()
      : industries;

  if (dv.fund_cny > 0) {
    rows.push({ name: "基金（未拆底层）", value: dv.fund_cny });
  }
  if (dv.unmapped_cny > 0) {
    rows.push({ name: "未映射直持", value: dv.unmapped_cny });
  }
  // 现金等价物单列：与「未映射」不是一回事（无股票敞口 ≠ 数据缺口）
  if (dv.cash_equivalent_cny > 0) {
    rows.push({ name: "现金等价物", value: dv.cash_equivalent_cny });
  }
  return rows;
});

const viewHint = computed(() =>
  view.value === "direct"
    ? "持仓结构：基金整块显示为「基金」不拆底层——这张图回答「我自己直接买了什么」。"
    : "穿透持仓：基金按底层持仓并入行业——这张图回答「我的钱最终押在哪些行业」。"
);

/** 持仓结构缺映射时的成因提示；无缺口或不在该视图时为空 */
const mappingHint = computed(() => {
  const dv = props.data.direct_view;
  if (view.value !== "direct" || dv.mapping_available) return "";
  return dv.unmapped_reason ?? "";
});
</script>

<style scoped>
.panel-subtitle {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

/* 标题与分段控件同一行，提示语单独一行降权 */
.panel-head {
  display: flex;
  gap: var(--space-standard);
  align-items: center;
  justify-content: space-between;
}

.panel-view-hint {
  margin: 0 0 var(--space-compact);
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* 环形图容器：与条形列表同高，切换时不产生跳动（饼图半径按容器短边算，
   240px 是「不再显小、又不把卡片拉长」的折中） */
.structure-donut {
  min-height: 240px;
}
</style>
