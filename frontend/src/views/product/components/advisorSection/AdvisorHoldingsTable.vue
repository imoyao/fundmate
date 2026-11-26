<script setup lang="ts">
import { computed, ref } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { AdvisorHoldingItem, AdvisorHoldingsResult } from "@/api/funds";
import { productRoute } from "@/utils/productIdentity";
import { centsToYuan, formatAmount } from "@/utils/currency";
import { DASH, type HeldPosition } from "./advisorModel";

/**
 * 投顾组合 · 成分基金（重设计 §03，行栈改真表格）。
 *
 * ## 为什么从行栈改回表格
 *
 * 行栈（三列 `minmax(0,1fr) 72px`）解决的是「名称贴左、数字钉右、百分比右缘对齐」，
 * 但它扫不出**集中度**：12 只基金的权重是一列孤立的百分数，用户要自己找最大的三个、
 * 自己相加。改成表格后权重列带条内条、默认按占比降序、表头直接给「前三大合计」——
 * 「这只组合有多集中」一眼可得。
 *
 * ## 「我的持仓」列为什么给金额和占比，而不是一个「已持有」标签
 *
 * 2026-11-26 用户实测：「只是已持有这个状态肯定不够，假如买的观察仓，有什么价值呢，
 * 所以要一眼看到。」同一只基金，我买了 500 元还是 5 万元，对「要不要跟这个组合」
 * 是不同的答案 —— 状态是二元的，仓位才是可判断的。
 *
 * 该列数据来自**对比端点**（`overlap.common`，带我的市值）。未登录 / 对比取不到时，
 * 这一列是**未知**而不是「都没持有」——两者对用户是天差地别的结论（后者会让人以为
 * 自己与该组合零重合）。故入参用 `Record | null`：null 渲染「—」，不渲染「未持有」。
 */
const props = defineProps<{
  holdings: AdvisorHoldingsResult | null;
  /**
   * 我持有的成分基金 → **我的市值 + 占我权益仓位比例**（来自对比端点）；
   * null = 未知，不写成「未持有」。
   */
  heldByCode: Record<string, HeldPosition> | null;
}>();

const sortDesc = ref(true);

const heldMap = computed(() =>
  props.heldByCode ? new Map(Object.entries(props.heldByCode)) : null
);

/** 占比缺失的排最后（不参与比较，避免 NaN 排序把行序打乱） */
const rows = computed<AdvisorHoldingItem[]>(() => {
  const list = [...(props.holdings?.holdings ?? [])];
  list.sort((a, b) => {
    if (a.after_ratio == null && b.after_ratio == null) return 0;
    if (a.after_ratio == null) return 1;
    if (b.after_ratio == null) return -1;
    return sortDesc.value
      ? b.after_ratio - a.after_ratio
      : a.after_ratio - b.after_ratio;
  });
  return list;
});

/** 条内条的分母：最大权重。用最大值而不是 100，让 15.98% 也看得出「这是最大的一只」 */
const maxRatio = computed(() =>
  rows.value.reduce((max, row) => Math.max(max, row.after_ratio ?? 0), 0)
);

/** 前三大合计：集中度是这一块最该被读到的结论 */
const top3Sum = computed(() => {
  const sorted = [...(props.holdings?.holdings ?? [])]
    .map(h => h.after_ratio ?? 0)
    .sort((a, b) => b - a)
    .slice(0, 3);
  return sorted.reduce((sum, value) => sum + value, 0);
});

const summary = computed(() => {
  const parts: string[] = [];
  if (rows.value.length) parts.push(`${rows.value.length} 只`);
  if (top3Sum.value > 0) parts.push(`前三大 ${top3Sum.value.toFixed(2)}%`);
  if (props.holdings?.as_of_date)
    parts.push(`快照 ${props.holdings.as_of_date}`);
  return parts.join(" · ");
});

function nameOf(item: AdvisorHoldingItem): string {
  return item.fund_name || item.fund_code;
}

function ratioText(item: AdvisorHoldingItem): string {
  return item.after_ratio != null ? `${item.after_ratio.toFixed(2)}%` : DASH;
}

function barWidth(item: AdvisorHoldingItem): string {
  const ratio = item.after_ratio ?? 0;
  if (maxRatio.value <= 0) return "0%";
  return `${Math.max((ratio / maxRatio.value) * 100, 2).toFixed(1)}%`;
}

/** 已持有 / 未持有 / 未知（null）三态 */
function heldState(item: AdvisorHoldingItem): "yes" | "no" | "unknown" {
  if (!heldMap.value) return "unknown";
  return heldMap.value.has(item.fund_code) ? "yes" : "no";
}

function heldOf(item: AdvisorHoldingItem): HeldPosition | null {
  return heldMap.value?.get(item.fund_code) ?? null;
}

/**
 * 我的持仓金额（整数元 + 千分位）。
 *
 * 取整而不是两位小数：这一列要回答「是观察仓还是真仓位」，元位足够区分量级，
 * 角分只会在窄列里把数字挤成折行。需要精确值时可看 title 全精度。
 */
function heldAmount(item: AdvisorHoldingItem): string {
  const pos = heldOf(item);
  return pos ? `¥${formatAmount(centsToYuan(pos.cents), 0)}` : "";
}

/** 全精度金额，挂 title（鼠标悬停可核对到分） */
function heldAmountTitle(item: AdvisorHoldingItem): string {
  const pos = heldOf(item);
  return pos ? `¥${formatAmount(centsToYuan(pos.cents), 2)}` : "";
}

/** 占我权益仓位的比例；分母非正时没有比例，只显示金额 */
function heldPct(item: AdvisorHoldingItem): string {
  const pct = heldOf(item)?.pct;
  return pct == null ? "" : `占我 ${pct.toFixed(1)}%`;
}
</script>

<template>
  <CardBlock class="advisor-holdings">
    <SectionHeader title="成分基金">
      <template #action>
        <div class="advisor-holdings__bar">
          <span class="advisor-holdings__summary">{{ summary }}</span>
          <el-button
            v-if="rows.length > 1"
            text
            size="small"
            class="advisor-holdings__sort"
            @click="sortDesc = !sortDesc"
          >
            {{ sortDesc ? "占比降序" : "占比升序" }}
          </el-button>
        </div>
      </template>
    </SectionHeader>

    <p v-if="!rows.length" class="advisor-holdings__hint">
      平台未披露该组合的成分基金
    </p>

    <div v-else class="advisor-holdings__wrap">
      <table class="detail-table advisor-holdings__table">
        <caption class="advisor-holdings__caption">
          组合成分基金及其权重，含是否已持有
        </caption>
        <colgroup>
          <col />
          <col class="advisor-holdings__col-w" />
          <col class="advisor-holdings__col-held" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">基金</th>
            <!-- 数字列一律走 .detail-table__num（共享约定，见 style/_detail-table.scss） -->
            <th scope="col" class="detail-table__num">权重</th>
            <th scope="col">我的持仓</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in rows" :key="item.fund_code">
            <td>
              <span class="fund">
                <RouterLink
                  v-if="item.in_local_db"
                  :to="
                    productRoute({ assetType: 'fund', symbol: item.fund_code })
                  "
                  class="fund__name fund__name--link"
                  :title="nameOf(item)"
                >
                  {{ nameOf(item) }}
                </RouterLink>
                <span v-else class="fund__name" :title="nameOf(item)">
                  {{ nameOf(item) }}
                </span>
                <span class="fund__code">{{ item.fund_code }}</span>
                <!-- 未收录本地名录时给灰标：点进去是 404，不如不给链接 -->
                <span v-if="!item.in_local_db" class="fund__flag">未收录</span>
              </span>
            </td>
            <td class="detail-table__num">
              <span class="weight">
                <span class="weight__bar" aria-hidden="true">
                  <span
                    class="weight__fill"
                    :style="{ width: barWidth(item) }"
                  />
                </span>
                <span class="weight__num">{{ ratioText(item) }}</span>
              </span>
            </td>
            <td>
              <span v-if="heldState(item) === 'yes'" class="held">
                <span class="held__amount" :title="heldAmountTitle(item)">{{
                  heldAmount(item)
                }}</span>
                <span v-if="heldPct(item)" class="held__pct">
                  {{ heldPct(item) }}
                </span>
              </span>
              <span v-else-if="heldState(item) === 'no'" class="held-none">
                未持有
              </span>
              <span v-else class="held-none">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.advisor-holdings__bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  justify-content: flex-end;
}

.advisor-holdings__summary {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.advisor-holdings__sort {
  font-size: var(--text-label);
}

.advisor-holdings__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-holdings__wrap {
  overflow-x: auto;
}

/* 列宽固定，名称列吃剩余空间：不固定的表在窄屏会把权重条压成一条线 */
.advisor-holdings__table {
  min-width: 480px;
  table-layout: fixed;
}

.advisor-holdings__col-w {
  width: 220px;

  @include bp.below("md") {
    width: 150px;
  }
}

.advisor-holdings__col-held {
  /* 两行（金额 + 占比）需要比单个「已持有」标签更宽；窄屏靠外层 wrap 横滚兜底 */
  width: 116px;
}

/* 行高对齐 design.md 的 43px（表头单独收窄，避免首行过高） */
.advisor-holdings__table tbody td {
  height: 43px;
}

/* 表格说明只给读屏；视觉上表头已经把信息说完了 */
.advisor-holdings__caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  white-space: nowrap;
  clip-path: inset(50%);
}

.fund {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  min-width: 0;
}

/* 名称允许收缩 + 省略：长基金名在固定列宽下必须先让位给代码与标记 */
.fund__name {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.fund__name--link {
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.fund__code {
  flex: 0 0 auto;
  font-family: var(--font-number);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.fund__flag {
  flex: 0 0 auto;
  padding: 0 var(--space-1);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-xs);
}

.weight {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 56px;
  gap: var(--space-2);
  align-items: center;
  max-width: 190px;
}

.weight__bar {
  height: 6px;
  overflow: hidden;
  background: var(--bg-muted);
  border-radius: 2px;
}

.weight__fill {
  display: block;
  height: 100%;
  background: color-mix(in srgb, var(--color-primary) 78%, transparent);
  border-radius: 2px;
}

/* 右对齐来自 `.detail-table__num`（td 上的共享约定），这里只管字重与字色 */
.weight__num {
  font-family: var(--font-number);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

/* 已持有：金额为主（等宽数字）、占比为辅，两行。
   用主色系而**不用**成功绿：绿色在本仓是「跌」，绿字会被读成在跌。 */
.held {
  display: flex;
  flex-direction: column;
  gap: 1px;
  line-height: 1.3;
}

.held__amount {
  font-size: var(--text-small);
  font-variant-numeric: tabular-nums;
  color: var(--color-primary-ink);
  white-space: nowrap;
}

.held__pct {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.held-none {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}
</style>
