<!--
  行业分布区（#2617）：两档口径切换 + 条形列表。

  为什么必须在同一个区块里放切换而不是两张图并排：「直接持有」把基金当整块、
  「穿透后」把基金拆到行业，两张图的分母与量级都不同，并排会诱导读者相加。
  切换式交互强制一次只看一个口径，提示语说明当前这张图回答的是哪个问题。

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
        aria-label="行业口径"
      />
    </div>
    <p class="panel-view-hint">{{ viewHint }}</p>
    <!-- 诚实降级：主口径没有「个股→行业」映射时直持图必然为空，
         把后端给的成因原样透出，避免用户把空图读成计算缺陷 -->
    <SoftBanner
      v-if="mappingHint"
      class="mb-2"
      variant="info"
      icon="ep:info-filled"
    >
      {{ mappingHint }}
    </SoftBanner>
    <p
      v-if="!rows.length"
      class="text-sm"
      :style="{ color: 'var(--text-secondary)' }"
    >
      暂无可用的行业配置数据。
    </p>
    <PenetrationBarList v-else :rows="rows" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import PenetrationBarList from "./PenetrationBarList.vue";
import { barWidth, percent } from "./format";
import type { PenetrationData } from "@/api/summary";

const props = defineProps<{ data: PenetrationData }>();

/** 两档口径：直接持有（基金整块）/ 穿透后（基金并入行业）。
 *  默认穿透后 = 既有行为，不改变旧用户的阅读习惯。 */
const VIEW_OPTIONS = [
  { label: "直接持有", value: "direct" },
  { label: "穿透后", value: "penetrated" }
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
 * #2617 直接持有口径：直持行业 + 基金整块 + 未映射直持 + 现金等价物。
 * 各项合计 = 持仓总市值；比率与金额都由后端算好（含 `fund_ratio` /
 * `unmapped_ratio`），前端不做除法——否则与「穿透后」图的口径会各算各的。
 */
const directRows = computed(() => {
  const dv = props.data.direct_view;
  const rows = dv.industries.map(row => ({
    key: row.code,
    name: row.name,
    title: `直持 ${row.name}（${row.code}）`,
    width: barWidth(row.ratio_of_total),
    value: percent(row.ratio_of_total)
  }));
  if (dv.fund_cny > 0) {
    rows.push({
      key: "__fund__",
      name: "基金（未拆底层）",
      title: "基金整块市值；其底层行业敞口见「穿透后」口径",
      width: barWidth(dv.fund_ratio),
      value: percent(dv.fund_ratio)
    });
  }
  if (dv.unmapped_cny > 0) {
    rows.push({
      key: "__unmapped__",
      name: "未映射直持",
      title: "没有行业映射的直持证券（不凭空补 0 值行业）",
      width: barWidth(dv.unmapped_ratio),
      value: percent(dv.unmapped_ratio)
    });
  }
  // 现金等价物单列：与「未映射」不是一回事（无股票敞口 ≠ 数据缺口）
  if (dv.cash_equivalent_cny > 0) {
    rows.push({
      key: "__cash__",
      name: "现金等价物",
      title: "货基/逆回购，本质无股票敞口（非缺口）",
      width: barWidth(dv.cash_equivalent_ratio),
      value: percent(dv.cash_equivalent_ratio)
    });
  }
  return rows;
});

const rows = computed(() =>
  view.value === "direct" ? directRows.value : penetratedRows.value
);

const viewHint = computed(() =>
  view.value === "direct"
    ? "直接持有：基金整块显示为「基金」不拆底层——这张图回答「我自己直接买了什么」。"
    : "穿透后：基金按底层持仓并入行业——这张图回答「我的钱最终押在哪些行业」。"
);

/** 直持视图缺映射时的成因提示；无缺口或不在直持视图时为空 */
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
</style>
