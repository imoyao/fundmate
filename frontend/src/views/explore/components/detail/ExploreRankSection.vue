<script setup lang="ts">
// 行业 / 赛道排行（#1431）：单一卡片承载「一级分类（申万行业 / 热门赛道）× 二级视图
// （拥挤度 / 乖离率）」，避免多张大表纵向堆叠；赛道维度无乖离率，切换分类时自动回到拥挤度。
//
// 数据层在 useRankTables（三张表同一接口，只有 source 不同）。
import { onMounted } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { RANK_LEGEND, useRankTables } from "./useRankTables";
import CrowdingTable from "./CrowdingTable.vue";
import BiasTable from "./BiasTable.vue";
import IndustryCrowdingTrend from "../IndustryCrowdingTrend.vue";

const {
  rankCategory,
  rankView,
  rankCategoryOptions,
  rankViewOptions,
  activeRankView,
  activeCrowdingItems,
  activeCrowdingLoading,
  biasItems,
  biasLoading,
  switchCategory,
  onRankViewChange,
  fetchRankTables
} = useRankTables();

onMounted(() => {
  // #1546 T2.1：三张表并发取数（原为串行 await，首尾相接）
  void fetchRankTables();
});
</script>

<template>
  <CardBlock class="industry-rank-section">
    <SectionHeader title="行业 / 赛道排行" :info="activeRankView.info">
      <template #action>
        <!-- 排行分类 / 视图切换（#1731 收敛）：原手写 `.rank-switch` 是「D13 果冻胶囊」外观
             （透明底 + 1px 边框 + `style-pop` 回弹），与 SegmentedControl 语义完全重叠
             （都是「多选一、选项少」），按 #1731 裁决收编到唯一实现。
             布局钩子改名 `.rank-switch-slot`——旧名会让人以为控件实现还在这里。 -->
        <SegmentedControl
          class="rank-switch-slot"
          :model-value="rankCategory"
          :options="rankCategoryOptions"
          size="small"
          aria-label="排行分类切换"
          @change="switchCategory"
        />
        <SegmentedControl
          class="rank-switch-slot"
          :model-value="rankView"
          :options="rankViewOptions"
          size="small"
          aria-label="排行视图切换"
          @change="onRankViewChange"
        />
        <span class="rank-updated"
          >更新：{{ activeRankView.date || "暂无" }}</span
        >
        <el-tooltip
          v-if="activeRankView.stale"
          :content="activeRankView.staleTip"
          placement="top"
        >
          <span class="rank-stale-pill">数据滞后</span>
        </el-tooltip>
      </template>
    </SectionHeader>

    <!-- 分位色标图例：提升表格可读性（配色仍用本站温度语义色，不引入外部色板） -->
    <div class="rank-legend">
      <span
        v-for="item in RANK_LEGEND"
        :key="item.label"
        class="rank-legend__item"
      >
        <i class="rank-legend__dot" :class="item.dotClass" />{{ item.label }}
      </span>
    </div>

    <CrowdingTable
      v-show="rankView === 'crowding'"
      embedded
      :items="activeCrowdingItems"
      :loading="activeCrowdingLoading"
      :name-column-label="rankCategory === 'track' ? '赛道' : '行业'"
      :show-bias-columns="rankCategory === 'sw'"
    />
    <BiasTable
      v-if="rankCategory === 'sw'"
      v-show="rankView === 'bias'"
      embedded
      :items="biasItems"
      :loading="biasLoading"
    />
  </CardBlock>

  <!-- 拥挤度趋势（周度 / 月度；随上方分类联动「申万行业 / 热门赛道」）
       跟在排行卡后面、共用 rankCategory —— 所以一起放在本组件（多根片段，不包 wrapper），
       而不是让父层为了传一个 category 再把 composable 实例化一遍。 -->
  <IndustryCrowdingTrend :category="rankCategory" />
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* ============================================================
   行业排行（#1431）：拥挤度 / 乖离率双视图共用一张卡片
   卡片外观统一由 CardBlock 提供（docs/design/components.md「CardBlock · 区块卡片容器」），
   本页只保留区块外边距，禁在此重复手写 token 卡片样式
   ============================================================ */
.industry-rank-section {
  margin-bottom: 24px;
}

.rank-updated {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.rank-stale-pill {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: var(--text-label);
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-warning-ink);
  white-space: nowrap;
  cursor: help;
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-radius: 6px 6px 6px 0;
}

/* 排行分类 / 视图分段控制（#1731 收敛）：外观全部由 SegmentedControl `small` 档负责，
   此处**只保留操作槽布局**（与右侧更新时间之间留 12px）。
   原「D13 果冻胶囊」手写块（透明底 + 1px 边框 + `style-pop` 回弹 + `:active` 缩放）已删除——
   它与 SegmentedControl 语义完全重叠，按 #1731 裁决收编。 */
.rank-switch-slot {
  margin-right: 12px;
}

/* ============================================================
   窄屏修溢出（#1585）：行业/赛道排行的区块标题行
   ------------------------------------------------------------
   WHY：操作槽里塞了「分类胶囊组 + 视图胶囊组 + 更新时间 + 滞后提示」，
   自然宽度约 414px；而公共 `SectionHeader` 的 `.section-header__action` 是
   `inline-flex; flex-shrink: 0`，`.section-header` 又是默认 `nowrap` 的 flex 行——
   两者叠加后这一行**既不能换行也不能收缩**，320/375 视口下把卡片（进而把文档）撑破：
   实测文档级横向溢出 155px（#1576 记录）→ #1583 修内边距后 147px → **本块清零**。

   只在**本区块**放开（不动公共 `SectionHeader`）：改公共组件会让 Aggregation /
   inventory 等所有带操作槽的页面一起变版，属另一条决策；那里的同类风险已登记。
   ============================================================ */
@include bp.below("sm") {
  :deep(.section-header) {
    flex-wrap: wrap;
    row-gap: 8px;
  }

  :deep(.section-header__action) {
    /* 覆盖公共组件的 `flex-shrink: 0`：允许收缩到容器宽并**内部换行** */
    flex: 1 1 100%;
    flex-wrap: wrap;
    row-gap: 8px;
    min-width: 0;
  }

  .rank-switch-slot {
    margin-right: 0; /* 独占一行时右侧不需要让位 */
  }
}

/* 排行分类 / 视图的胶囊外观与 style-pop 回弹关键帧已随 #1731 收敛删除：
   它们与 SegmentedControl 的软按钮规范语义重叠，保留任一份都会让两套外观并存。 */

/* ============================================================
   分位色标图例（#1431）
   ============================================================ */
.rank-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 10px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.rank-legend__item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.rank-legend__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.rank-legend__dot--low {
  background: var(--temp-low);
}

.rank-legend__dot--mid {
  background: var(--temp-mid);
}

.rank-legend__dot--high {
  background: var(--temp-high);
}

/* 表格视觉基线由全站统一主题维护（src/style/el-table.css），勿在本页 :deep 覆盖 */
</style>
