<template>
  <div class="fund-ranking-page min-h-full">
    <PageHeaderBar
      title="同类优选"
      subtitle="基于你的持仓与自选的基金，在同一类型内按风险收益指标排序——风险比跨类别不可比，故不做全市场榜"
    />

    <div class="ranking-shell">
      <PageSkeleton v-if="initialLoading" :cards="1" :table-rows="6" />

      <template v-else>
        <CardBlock>
          <SectionHeader :title="rankingTitle" :info="rankingInfo" />

          <!-- 表格工具栏（#1714「一层页头」原则的卡片内变体）：筛选器收进表格，
               不再单独占一张卡片——筛选与数据同卡，关联才不断裂 -->
          <div class="ranking-toolbar">
            <div class="filter-item">
              <label class="filter-item__label" for="fund-type">基金类型</label>
              <el-select
                id="fund-type"
                v-model="selectedTypeId"
                class="filter-item__control"
                placeholder="选择一个类型"
                filterable
                :loading="typesLoading"
                @change="onTypeChange"
              >
                <el-option
                  v-for="t in typeOptions"
                  :key="t.fund_type_id"
                  :value="t.fund_type_id"
                  :label="`${t.name}（共 ${t.count} 只）`"
                />
              </el-select>
            </div>

            <div class="ranking-toolbar__meta">
              <!-- 单位统一说明：表头去掉 (%) 后由这里兜底，表头更短不被截断 -->
              <span class="unit-note">
                收益 / 回撤 / UI 列单位为 %；夏普、卡玛、波回比为比率
              </span>
              <!-- 剔除提示：从整行长条降级为标题级图标气泡，纵向空间还给表格 -->
              <el-tooltip
                v-if="excludedDistorted > 0"
                placement="top"
                :content="excludedTip"
              >
                <span
                  class="excluded-tip"
                  role="img"
                  :aria-label="excludedTip"
                  tabindex="0"
                >
                  <IconifyIconOffline icon="ep:warning-filled" />
                  {{ excludedDistorted }} 只被剔除
                </span>
              </el-tooltip>
            </div>
          </div>

          <!-- 诚实降级：没有可选类型时，说明的是「没人算过」而不是「没有基金」 -->
          <p v-if="!typeOptions.length" class="empty-hint">
            暂无风险指标快照。榜单需要先跑一次
            <code>pdm run sync --job fund_risk_metrics</code> 生成同类指标。
          </p>

          <div v-else-if="rankingLoading" class="table-loading">
            <el-skeleton :rows="5" animated />
          </div>

          <div v-else-if="!rows.length" class="empty-hint">
            {{ noRowHint }}
          </div>

          <FundRankingTable
            v-else
            :rows="rows"
            :table-columns="tableColumns"
            :column-groups="columnGroups"
            :metric="metric"
            :order="order"
            @sort="onSort"
            @open="goDetail"
          />

          <p class="footnote">
            指标窗口「{{ windowLabel }}」：夏普 / 卡玛 / 波回比 / UI / 最大回撤
            / 年化收益均按该窗口计算；近1月 / 近3月 /
            近1年为区间净值涨跌幅。样本数 {{ sampleRange }} 个交易日 · 口径版本
            {{ caliberVersion ?? "—" }} · 数据截至
            {{ asOfDate }}。榜单是同类内的相对排序，**不构成投资建议**。
          </p>

          <!-- 指标说明兜底（2026-10-17）：默认态表头只有文字，深度学习需求
               由底部折叠面板承接——比满屏 i 图标安静，比底部文档卡近。 -->
          <el-collapse v-model="metricGuideOpen" class="metric-guide">
            <el-collapse-item name="guide">
              <template #title>
                <span class="metric-guide__title">指标说明与排序方向</span>
              </template>
              <dl class="metric-guide__list">
                <div
                  v-for="col in tableColumns"
                  :key="col.key"
                  class="metric-guide__row"
                >
                  <dt>
                    {{ col.label }}
                    <span class="metric-guide__dir">{{
                      dirLabel(col.dir)
                    }}</span>
                  </dt>
                  <dd>{{ col.desc }}</dd>
                </div>
              </dl>
            </el-collapse-item>
          </el-collapse>
        </CardBlock>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
// 同类优选：自选页的深度体检层（页面语义与口径纪律见文件头注释）。
//
// #980 拆分后的分工——本文件只做装配与页面级文案：
// - 列定义（列即排序入口）→ ./rankingColumns.ts
// - 数值单元格口径（格式化 / 涨跌色 / 数据条）→ ./rankingCells.ts（纯函数，可单测）
// - 状态 · 派生 · 取数 → ./composables/useFundRanking.ts
// - 表格结构 · sticky 列 · 双层表头 → ./components/FundRankingTable.vue
// - 基金单元格（名称 / 代码 / 徽章）→ ./components/FundRankingNameCell.vue
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { dirLabel } from "./rankingCells";
import { columnGroups, tableColumns } from "./rankingColumns";
import { useFundRanking } from "./composables/useFundRanking";
import FundRankingTable from "./components/FundRankingTable.vue";

// 与路由 `router/modules/asset.ts` 的 name 一致，保证 keep-alive 命中
defineOptions({ name: "AssetFundRanking" });

// 状态与派生全部来自 useFundRanking；解构成同名变量，模板逐字不变（#980 拆分纪律）。
const {
  initialLoading,
  typesLoading,
  rankingLoading,
  typeOptions,
  selectedTypeId,
  metric,
  order,
  rows,
  excludedDistorted,
  caliberVersion,
  metricGuideOpen,
  rankingTitle,
  rankingInfo,
  excludedTip,
  noRowHint,
  windowLabel,
  asOfDate,
  sampleRange,
  onTypeChange,
  onSort,
  goDetail
} = useFundRanking({ tableColumns });
</script>

<style lang="scss" scoped>
.fund-ranking-page {
  background: var(--bg-page);
}

.ranking-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding-top: var(--space-4);
}

/* ── 表格工具栏：筛选器与数据同卡（2026-10-17，原独立「筛选」卡片撤销） ── */
.ranking-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: var(--space-4);

  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    align-items: center;
  }
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);

  &__label {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &__control {
    min-width: 240px;
  }
}

.unit-note {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.excluded-tip {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 8px;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
  white-space: nowrap;
  cursor: help;
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

.empty-hint {
  padding: var(--space-5) 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;

  code {
    padding: 0 4px;
    font-family: var(--font-mono, monospace);
    background: var(--bg-subtle);
    border-radius: var(--radius-xs);
  }
}

.table-loading {
  padding: var(--space-4) 0;
}

.footnote {
  margin-top: var(--space-4);
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-tertiary-ink);
}

/* 底部指标说明折叠面板（2026-10-17）：替代「满屏 i 图标 + 跳底部文档卡」，
   默认收起，需要时展开；口径与方向一次讲全。 */
.metric-guide {
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-subtle, var(--border-light));

  &__title {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-secondary);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
  }

  &__row {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: var(--space-4);

    dt {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: var(--text-label);
      font-weight: 600;
      color: var(--text-primary);
    }

    dd {
      margin: 0;
      font-size: var(--text-label);
      line-height: 1.7;
      color: var(--text-secondary);
    }
  }

  &__dir {
    font-size: var(--text-label);
    font-weight: 400;
    color: var(--text-tertiary-ink);
  }
}
</style>
