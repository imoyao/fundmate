<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { FundHoldingsDetailResult } from "@/api/products";

/**
 * 详情页「持仓明细」区块（#2029 卡 C · 设计卡 §4.1 #5）。
 *
 * 表格：代码 / 名称 / 占净值比 / 持股数 / 市值 / 排名，数据来自
 * `GET /api/products/fund-holdings-detail/`。
 *
 * 口径与降级（设计卡 §4.2③ · penetration 硬口径 7）：
 * - **必须展示 `basis_label`** —— 季报只披露前十大，`top10` 与 `full` 不可混。
 *   不标注的话用户会把「只披露了 10 只」误读成「只买了 10 只」，据此判断
 *   持仓集中度会得出完全错误的结论。
 * - 缺失字段逐项降级为「—」，**不按 0 展示**（0 意味着「确实没配这只」，
 *   缺失只是「没采到」，两者语义相反）。
 *
 * ## 渐进披露：为什么折叠，以及折叠不能碰什么
 *
 * 库内实测（2026-10-12）：`fund_holdings` 最新报告期共 113 只基金，其中
 * **112 只是 `full` 口径，中位 67 行、最大 100 行**，全部超过 10 行；`top10`
 * 口径仅 1 只。也就是说把整张表堆在页面上不是偶发，是主流形态——50~100 行的
 * 表格会把走势 / 业绩这些更受关注的区块挤到几屏之外。
 *
 * 折叠的是**展示层**，不能顺手改口径：
 * - `basis=top10` 是「数据本身只有前十大」，必须保留 ⚠️ caveat；
 * - `basis=full` 是「数据全，但表格长」，折叠只是视觉压缩，**没有 caveat**——
 *   若把两者混用同一个警告，用户会以为全量披露的基金也只披露了十只。
 *   故下方 ⚠️ 仍只由 `isTop10` 驱动，与折叠状态无关。
 * - 「所示合计」必须跟着**可见行**重算：折叠时若仍显示全量合计，标签写着
 *   「所示」就成了假的——用户把可见行加一遍会发现对不上。全量合计改由展开
 *   按钮带出，折叠状态下用户也能知道全貌。
 */

const props = defineProps<{
  detail: FundHoldingsDetailResult | null;
  source: string;
}>();

/** 折叠状态下预览的行数。取 10 是对齐季报「前十大」的既有心智，不另设魔数。 */
const PREVIEW_SIZE = 10;

const holdings = computed(() => props.detail?.holdings ?? null);
const allRows = computed(() => holdings.value?.rows ?? []);

/** `top10` 口径下必须提示：这是季报前十大，不等于全部持仓 */
const isTop10 = computed(() => holdings.value?.basis === "top10");

const expanded = ref(false);

/**
 * 展开状态跟随「口径 + 报告期 + 行数」复位：换产品时三者至少有一项变化，
 * 而在同一只基金上重新取数不会误收起用户刚展开的表。
 */
const resetKey = computed(
  () =>
    `${holdings.value?.basis ?? ""}|${holdings.value?.report_period ?? ""}|${allRows.value.length}`
);
watch(resetKey, () => {
  expanded.value = false;
});

/** 行数没超过预览量时不出按钮——「展开全部 12 只」这种按钮是纯噪声 */
const needToggle = computed(() => allRows.value.length > PREVIEW_SIZE);

const visibleRows = computed(() =>
  needToggle.value && !expanded.value
    ? allRows.value.slice(0, PREVIEW_SIZE)
    : allRows.value
);

/** 可见行的占比合计；占比全部缺失时为 null（此时不渲染合计行） */
const visibleTotalRatio = computed(() => {
  const vals = visibleRows.value
    .map(r => r.ratio)
    .filter((v): v is number => v != null);
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
});
</script>

<template>
  <CardBlock class="holding-section">
    <SectionHeader title="持仓明细" />

    <p v-if="!allRows.length" class="holding-section__hint">暂无持仓明细数据</p>

    <template v-else>
      <!-- 口径标注：与表格同屏，不藏在脚注里（用户第一眼就要看到「这是前十大」） -->
      <p v-if="holdings?.basis_label" class="holding-section__basis">
        披露口径：{{ holdings.basis_label }}
        <template v-if="holdings.report_period">
          · 报告期 {{ holdings.report_period }}
        </template>
      </p>

      <!-- 展开后给滚动容器，**只在真的会有上百行时**才加高度上限：
           10 行的折叠态不需要一个可能冒出滚动条的盒子。 -->
      <div
        class="holding-section__table-wrap"
        :class="{
          'holding-section__table-wrap--scroll': expanded && needToggle
        }"
      >
        <table id="holding-detail-table" class="holding-section__table">
          <thead>
            <tr>
              <th scope="col" class="holding-section__num">序号</th>
              <th scope="col">代码</th>
              <th scope="col">名称</th>
              <th scope="col" class="holding-section__num">占净值比</th>
              <th scope="col" class="holding-section__num">持股数(万股)</th>
              <th scope="col" class="holding-section__num">市值(万元)</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(r, i) in visibleRows"
              :key="r.stock_code + '-' + (r.rank ?? i)"
            >
              <td class="holding-section__num">
                {{ r.rank ?? i + 1 }}
              </td>
              <td class="holding-section__code">
                {{ r.stock_code }}
              </td>
              <td>{{ r.stock_name ?? "—" }}</td>
              <td class="holding-section__num">
                {{ r.ratio != null ? r.ratio.toFixed(2) + "%" : "—" }}
              </td>
              <td class="holding-section__num">
                {{ r.shares != null ? r.shares.toLocaleString() : "—" }}
              </td>
              <td class="holding-section__num">
                {{
                  r.market_value != null ? r.market_value.toLocaleString() : "—"
                }}
              </td>
            </tr>
          </tbody>
          <tfoot v-if="visibleTotalRatio != null">
            <tr>
              <th scope="row" colspan="3">所示合计</th>
              <td class="holding-section__num">
                {{ visibleTotalRatio.toFixed(2) }}%
              </td>
              <td class="holding-section__num">—</td>
              <td class="holding-section__num">—</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <button
        v-if="needToggle"
        type="button"
        class="holding-section__more"
        :aria-expanded="expanded"
        aria-controls="holding-detail-table"
        @click="expanded = !expanded"
      >
        {{ expanded ? "收起" : `展开全部 ${allRows.length} 只` }}
        <!-- 折叠状态下也给出全量合计：用户不必为了看一眼总占比而先展开上百行 -->
        <span v-if="!expanded && holdings?.shown_total_ratio != null">
          （合计 {{ holdings.shown_total_ratio.toFixed(2) }}%）
        </span>
      </button>

      <p v-if="isTop10" class="holding-section__caveat">
        ⚠️ 以上为季报披露的前十大重仓，不代表该基金的全部持仓。
      </p>
      <p class="holding-section__footnote">
        数据来源：{{ source }} · 持仓为报告期快照（非日期序列）
        <template v-if="holdings?.report_date">
          · 截至 {{ holdings.report_date }}</template
        >
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.holding-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.holding-section__hint,
.holding-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.holding-section__basis {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

/* ⚠️ 口径警告：这是**用户必须看到**的信息，不能做成不显眼的脚注 */
.holding-section__caveat {
  padding: var(--space-2) var(--space-3);
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--bg-subtle, var(--bg-card));
  border-left: 3px solid var(--color-warning, var(--brand-700));
  border-radius: 0 var(--radius-sm, 4px) var(--radius-sm, 4px) 0;
}

.holding-section__table-wrap {
  overflow-x: auto;
}

/* 百来行的表不能无限撑高：给上限 + 表头吸附，靠滚动而不是靠拖垮整页 */
.holding-section__table-wrap--scroll {
  max-height: 420px;
  overflow-y: auto;
}

.holding-section__table {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}

.holding-section__table th,
.holding-section__table td {
  padding: var(--space-2) var(--space-2);
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-light);
}

.holding-section__table thead th {
  font-weight: 500;
  color: var(--text-tertiary);
}

/* 表头必须带底色：否则滚动时表格行会从 th 的透明缝隙里透出来 */
.holding-section__table-wrap--scroll thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-card);
}

.holding-section__num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.holding-section__code {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.holding-section__more {
  align-self: flex-start;
  padding: 0;
  font-size: 12px;
  color: var(--brand-700, var(--brand-500));
  cursor: pointer;
  background: none;
  border: none;
}

.holding-section__more:hover {
  text-decoration: underline;
}

.holding-section__more:focus-visible {
  outline: 2px solid var(--brand-500);
  outline-offset: 2px;
  border-radius: var(--radius-sm, 4px);
}
</style>
