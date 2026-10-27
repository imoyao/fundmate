<!--
  OverviewAssetsCard · 资产全景左卡（#980 批 B6 从 `OverviewSummaryCard.vue` 抽出）

  总资产 hero + 环比/同比 + 总负债/净资产/总盈亏三列。

  竖向节奏（原先踩过的坑）：一开始是 `flex flex-col justify-between h-full`，
  但右卡（280px 图表 + 标题行）比左卡内容高出一大截，`justify-between` 把这段
  高度差**全部**变成 hero 与底部三指标之间的空洞，三指标被顶到卡片最底边、
  看起来像掉队的一行。现为**整组垂直居中 + 固定紧凑间距**：剩余高度均分到上下
  两侧，卡片读起来是「有意留白」而不是「内容被撑散」。`h-full` 保留（与右卡等高
  是两卡并排的基本秩序），但它不再参与内部排布。
-->
<template>
  <div class="summary-card rounded-2xl p-6 h-full">
    <div class="summary-card__stack">
      <div class="summary-card__hero">
        <p class="summary-card__label">总资产（本月）</p>
        <!-- 总资产是**存量**不是盈亏：design.md「指标数值不染涨跌色」。
             `MoneyDisplay` 的 `auto-color` 默认开着，值 > 0 时会把 48px 的
             主数字染成涨红——主数字被染红既与语义不符，也让下面三列的中性
             基调被拉偏。故显式关掉 autoColor 并给 --text-primary。 -->
        <MoneyDisplay
          :value="totalAssets"
          size="hero"
          :show-sign="false"
          :show-currency="true"
          :auto-color="false"
          custom-color="var(--text-primary)"
        />
        <!-- 环比 / 同比：标签在前、数值在后（原先是「数值 较上月」）。
             「+1.24% 较上月」要回读一遍才知道是什么，「较上月 +1.24%」不用。 -->
        <div class="summary-card__deltas">
          <div class="summary-card__delta">
            <span class="summary-card__delta-label">较上月</span>
            <template v-if="latestSnapshot?.monthly_change_pct != null">
              <RiseFallText
                :value="latestSnapshot.monthly_change_pct"
                suffix="%"
                size="sm"
              />
            </template>
            <el-tooltip
              v-else
              content="暂无上月同期数据，持续使用后自动积累"
              placement="top"
            >
              <span class="summary-card__delta-none">——</span>
            </el-tooltip>
          </div>
          <div class="summary-card__delta">
            <span class="summary-card__delta-label">较去年同期</span>
            <template v-if="latestSnapshot?.yearly_change_pct != null">
              <RiseFallText
                :value="latestSnapshot.yearly_change_pct"
                suffix="%"
                size="sm"
              />
            </template>
            <el-tooltip
              v-else
              content="暂无去年同期数据，持续使用后自动积累"
              placement="top"
            >
              <span class="summary-card__delta-none">——</span>
            </el-tooltip>
          </div>
        </div>
      </div>

      <div class="summary-card__rule" />

      <!-- 三列之间用竖细线分隔而不是各给一个底色块：它们是同一组指标的
           三个并列视角，给底色块会读成三张独立小卡、反而割裂。 -->
      <div class="summary-card__metrics">
        <div class="summary-card__metric">
          <p class="summary-card__metric-label">总负债</p>
          <MoneyDisplay
            :value="totalLiabilities"
            size="md"
            :show-sign="false"
            :show-currency="true"
            :auto-color="false"
            custom-color="var(--text-primary)"
          />
        </div>
        <div class="summary-card__metric">
          <p class="summary-card__metric-label">净资产</p>
          <MoneyDisplay
            :value="totalAssets - totalLiabilities"
            size="md"
            :show-sign="false"
            :show-currency="true"
            :auto-color="false"
            custom-color="var(--text-primary)"
          />
        </div>
        <div class="summary-card__metric">
          <p class="summary-card__metric-label">总盈亏</p>
          <!-- 唯一保留涨红跌绿的一格：它本来就是盈亏口径 -->
          <MoneyDisplay :value="totalPnl" size="md" :show-currency="true" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { AssetSnapshotItem } from "@/api/summary";

defineOptions({ name: "OverviewAssetsCard" });

defineProps<{
  totalAssets: number;
  totalLiabilities: number;
  totalPnl: number;
  /** 最近一期快照；null = 还没有快照，环比同比都降级为「——」+ 说明气泡 */
  latestSnapshot: AssetSnapshotItem | null;
}>();
</script>

<style lang="scss" scoped>
@use "./summary-card" as *;

.summary-card__stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
  justify-content: center;
  height: 100%;
}

.summary-card__label {
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 环比 / 同比成对出现：行内两列，列间距 20px（4px 基数）。
   与上方大数字拉开 16px —— 这三行是「一个数 + 它的两个参照」，
   12px 会让参照读起来像数字的注解，20px 又只剩空。 */
.summary-card__deltas {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 16px;
}

.summary-card__delta {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
}

.summary-card__delta-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.summary-card__delta-none {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 卡片内部两级分割线：
   · 摘要区 → 三指标这一道是**结构性断点**，与卡片外框同重量（--border-light）；
   · 三列之间的竖线是**同级并列**的弱分隔，降到 --border-subtle（design.md：
     卡片内部降权分割线用它）。
   两级都走令牌，且竖线明显轻于横线——顺序反过来会让三列看起来像一张表格。 */
.summary-card__rule {
  height: 1px;
  background-color: var(--border-light);
}

.summary-card__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.summary-card__metric {
  min-width: 0;

  /* 竖线与两侧内容各留 16px：线是分隔，不是内容边界，贴上去会读成「线压着字」 */
  padding: 0 var(--space-compact);
}

.summary-card__metric:first-child {
  padding-left: 0;
}

.summary-card__metric:last-child {
  padding-right: 0;
}

.summary-card__metric + .summary-card__metric {
  border-left: 1px solid var(--border-subtle);
}

/* 标签与数字的层级：13px 辅助色标签 + 16px 主文字数字，标签不抢数字。
   6px 间距让「标签→数字」成为一组，而不是两行无关文字。 */
.summary-card__metric-label {
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
