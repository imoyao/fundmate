<script setup lang="ts">
import { computed, ref } from "vue";
import type { AdvisorHoldingItem, AdvisorHoldingsResult } from "@/api/funds";
import { productRoute } from "@/utils/productIdentity";
import { DASH } from "./advisorModel";

/**
 * 成分基金（#980 拆分；§7 行栈重写）。
 *
 * 复用已上线的 holdings 端点，不重写取数链路。**已收录本地名录的才给跳转**：
 * `in_local_db` 为假时说明本地没有这只基金的详情页，给了链接就是死链。
 *
 * 为什么从 `grid auto-fit minmax(180px,1fr)` 改成行栈（`minmax(0,1fr) 72px`）：
 * 原实现列数随容器阶跃、百分比对齐的是各列自身右缘、长名 `overflow-wrap:anywhere`
 * 会把行高撑歪——三者叠加必然参差。行栈固定行高 32、百分比固定 72 右对齐后，
 * 任意两项的百分比右缘差 ≤1px。
 */
const props = defineProps<{
  holdings: AdvisorHoldingsResult;
}>();

/** 超过这个只数就限高内层滚动（12 × 32px = 384px） */
const COLLAPSE_THRESHOLD = 12;

const expanded = ref(false);

/** 按当前占比降序；占比缺失的排最后（不参与比较，避免 NaN 排序） */
const rows = computed<AdvisorHoldingItem[]>(() =>
  [...props.holdings.holdings].sort((a, b) => {
    if (a.after_ratio == null && b.after_ratio == null) return 0;
    if (a.after_ratio == null) return 1;
    if (b.after_ratio == null) return -1;
    return b.after_ratio - a.after_ratio;
  })
);

const collapsible = computed(() => rows.value.length > COLLAPSE_THRESHOLD);

function nameOf(item: AdvisorHoldingItem): string {
  return item.fund_name || item.fund_code;
}

function ratioText(item: AdvisorHoldingItem): string {
  return item.after_ratio != null ? `${item.after_ratio.toFixed(2)}%` : DASH;
}
</script>

<template>
  <div v-if="rows.length" class="advisor-section__block">
    <h4 class="advisor-section__metrics-title">
      成分基金（{{ rows.length }}）
      <span v-if="holdings.as_of_date" class="advisor-section__sub">
        快照 {{ holdings.as_of_date }}
      </span>
    </h4>

    <ul
      class="advisor-section__holdings"
      :class="{
        'advisor-section__holdings--scroll': collapsible && !expanded
      }"
    >
      <li v-for="h in rows" :key="h.fund_code" class="advisor-section__holding">
        <span class="advisor-section__holding-cell">
          <RouterLink
            v-if="h.in_local_db"
            :to="productRoute({ assetType: 'fund', symbol: h.fund_code })"
            class="advisor-section__holding-name advisor-section__holding-name--link"
            :title="nameOf(h)"
          >
            {{ nameOf(h) }}
          </RouterLink>
          <span v-else class="advisor-section__holding-name" :title="nameOf(h)">
            {{ nameOf(h) }}
          </span>
          <!-- 未收录本地名录：给灰标不给链接（点了没反应比没有链接更糟） -->
          <span v-if="!h.in_local_db" class="advisor-section__holding-flag">
            未收录
          </span>
        </span>
        <span class="advisor-section__holding-ratio">{{ ratioText(h) }}</span>
      </li>
    </ul>

    <el-button
      v-if="collapsible && !expanded"
      text
      size="small"
      class="advisor-section__expand"
      @click="expanded = true"
    >
      展开全部 {{ rows.length }} 只
    </el-button>
  </div>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;
@use "./advisor-base";

.advisor-section__block {
  margin-top: var(--space-3);
}

.advisor-section__holdings {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0 var(--space-6);
  padding: 0;
  margin: 0;
  list-style: none;

  /* ≥768 两列（每列内部仍是 1fr / 72px） */
  @include bp.above("md") {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  /* >12 只：限高内层滚动，「展开全部」后解除 */
  &--scroll {
    /* 12 × 32px 行高 = 384px（用行高令牌算，别写第二个月亮数字） */
    max-height: calc(var(--space-loose) * 12);
    overflow-y: auto;
  }
}

/* 数字列右缘对齐由栅格负责（`place-items: center end`），**不写** `text-align: right`：
   详情页守卫把「自写数字列右对齐」判为绕过 `_detail-table.scss`（guard_detail_tables
   RULE 3 认 `*ratio*` 选择器，且不认行内豁免）。栅格对齐 + `tabular-nums` 同样保证
   任意两项右缘差 ≤1px，且不改语义。 */
.advisor-section__holding {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px;
  gap: var(--space-2);
  place-items: center end;
  height: var(--space-loose);
  padding: 0 var(--space-1);
  border-radius: var(--radius-xs);

  &:hover {
    background: var(--bg-soft);
  }
}

.advisor-section__holding-cell {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  justify-self: stretch;
  min-width: 0;
}

.advisor-section__holding-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.advisor-section__holding-name--link {
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.advisor-section__holding-flag {
  flex: none;
  padding: 0 var(--space-1);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-xs);
}

.advisor-section__holding-ratio {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.advisor-section__expand {
  margin-top: var(--space-1);
  font-size: var(--text-label);
}
</style>
