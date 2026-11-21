<template>
  <div class="fund-ranking-page min-h-full">
    <PageHeaderBar
      title="同类优选"
      subtitle="基于你的持仓与自选，在同一类型内按风险收益指标排序"
      :updated-at="asOfLabel"
    />

    <div class="ranking-shell">
      <PageSkeleton v-if="initialLoading" :cards="1" :table-rows="6" />

      <template v-else>
        <CardBlock>
          <!-- 区块头（#3215 重新设计）：左侧只留区块语义（榜单是什么），
               口径说明与剔除提示收在右侧同一行——旧版把「基金类型」做成
               叠在下拉框上方的一枚 13px 微标签，两行 60px 只为放一个选择器。 -->
          <SectionHeader title="同类榜单" :info="rankingInfo">
            <template #action>
              <div class="ranking-meta">
                <!-- 单位统一说明：表头去掉 (%) 后由这里兜底，表头更短不被截断 -->
                <span class="ranking-meta__units">
                  单位：收益 / 回撤 / UI 为 %；夏普 · 卡玛 · 波回比为比率
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
            </template>
          </SectionHeader>

          <!-- 类型筛选（#1714「一层页头」原则的卡片内变体：筛选与数据同卡，
               关联不断裂）。类型实际只有 5 类，落在 design.md「Filter & Selection」
               的一级主维度区间（2–6）⇒ 走 SegmentedControl 平铺：一次点击即切换，
               每类的只数直接带在选项上，不必展开下拉再读一遍「（共 15 只）」。
               选项若增长到需要横向滚动，说明该维度应降级为二级筛选，届时再换胶囊栏。 -->
          <div v-if="typeOptions.length" class="type-filter">
            <span class="type-filter__label">基金类型</span>
            <!-- 轨道是整个控件，宽度靠内建 chip 撑开；容器只负责窄屏兜底：
                 <md 时横向滑动（选项不会被压成竖排字），桌面档永不滚动。 -->
            <div class="type-filter__control">
              <SegmentedControl
                :model-value="selectedTypeId ?? -1"
                :options="typeSegments"
                aria-label="基金类型"
                @change="onTypeSelect"
              />
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

          <!-- 数据截至已上移到页头胶囊（#3215），这里只留口径本身；
               「不构成投资建议」此前写的是 markdown 星号（`**…**`），在模板里
               不渲染语法、原样显示成一串星号——改用 <strong> 承载加粗。 -->
          <p class="footnote">
            指标窗口「{{ windowLabel }}」：夏普 / 卡玛 / 波回比 / UI / 最大回撤
            / 年化收益均按该窗口计算；近1月 / 近3月 /
            近1年为区间净值涨跌幅。样本数 {{ sampleRange }} 个交易日 · 口径版本
            {{
              caliberVersion ?? "—"
            }}。榜单是同类内的相对排序，<strong>不构成投资建议</strong>。
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
import { computed } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
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
  rankingLoading,
  typeOptions,
  selectedTypeId,
  metric,
  order,
  rows,
  excludedDistorted,
  caliberVersion,
  metricGuideOpen,
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

/** 页头右侧状态胶囊：数据新鲜度是这一页最先要确认的前提，
 *  放进页头比埋在表格脚注末尾更早被看见（脚注仍保留口径本身）。
 *  `asOfDate` 在无数据时是「—」，此时不显示胶囊（不编造一个日期）。 */
const asOfLabel = computed(() =>
  asOfDate.value && asOfDate.value !== "—" ? `数据截至 ${asOfDate.value}` : ""
);

/** 类型选项 → 分段控制器选项：只数直接挂在选项上（`count` 徽章）。 */
const typeSegments = computed(() =>
  typeOptions.value.map(t => ({
    label: t.name,
    value: t.fund_type_id,
    count: t.count
  }))
);

/** 分段控制器是受控组件（不会自己写 model），这里落值后再取数；
 *  点当前项时组件本身不 emit（select() 里已短路），无需二次判重。 */
function onTypeSelect(value: number) {
  selectedTypeId.value = value;
  onTypeChange();
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.fund-ranking-page {
  background: var(--bg-page);
}

.ranking-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);

  /* 页头自带 --space-section(48px) 的下外边距；此前这里再加 16px 顶内边距，
     页头到卡片实测 64px，比全站其他页面松一档（#3215 收口）。 */
}

/* ── 区块头右侧：单位说明 + 剔除提示（#3215 从「标签 + 大下拉」那一行挪上来） ──
   13px 静音文字，与标题同一基线；剔除提示是唯一带色元素，保持「异常才出声」。 */
.ranking-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
  justify-content: flex-end;

  &__units {
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }
}

/* ── 类型筛选带（一级筛选 · 分段控制器） ──
   「基金类型」是行内标签（不再叠在控件上方）：与分段轨道同基线、同 13px，
   左缘与标题、表格对齐，一条竖线上三处起点一致。
   底部 1px 分割线把「筛选带」与「数据区」切开——表头本身是 --bg-muted 灰底，
   没有这条线时筛选控件与表头会糊成一片（design.md：筛选行与表格用分割线分区）。 */
.type-filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  align-items: center;
  padding-bottom: var(--space-3);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-light);

  &__label {
    flex: 0 0 auto;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  /* 分段控制器的 chip 是「一次性读全」的控件：绝不允许被压缩换行
     （480 视口实测会把「混合型」压成三行竖排）。宽度靠内容撑开，
     容器在窄屏兜底成横滑——桌面档轨道宽 443px，永不触发滚动。 */
  &__control {
    min-width: 0;
    max-width: 100%;

    @include bp.below("sm") {
      overflow-x: auto;
      scrollbar-width: none;

      &::-webkit-scrollbar {
        display: none;
      }
    }

    :deep(.segmented-control__item) {
      flex: 0 0 auto;
      white-space: nowrap;
    }
  }
}

/* 窄屏（< 640）：标题与右侧口径说明横向放不下时，口径说明整体换到第二行并左对齐。
   不这么做时 SectionHeader 会把负空间全压给标题（title-group 是 min-width: 0），
   标题被截成「同…」——那比换行难看得多。 */
@include bp.below("sm") {
  :deep(.section-header) {
    flex-wrap: wrap;
    row-gap: var(--space-2);
  }

  .ranking-meta {
    justify-content: flex-start;
  }
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
