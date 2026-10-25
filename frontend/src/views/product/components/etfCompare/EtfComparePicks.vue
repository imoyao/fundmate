<!-- 优选 ETF 小卡（#2334 形态 B）：对比表上方的速览层，最多 3 只 -->
<script setup lang="ts">
import { RouterLink } from "vue-router";
import {
  TRACKING_TITLE,
  pctClass,
  recommendLabel,
  trackingText,
  type EtfPick
} from "./etfCompareModel";

defineProps<{
  /** 已按名次升序、至多 3 只（空数组时父层整块不渲染） */
  picks: EtfPick[];
}>();
</script>

<template>
  <div class="etf-cmp__picks">
    <p class="etf-cmp__picks-title">优选 ETF</p>
    <ul class="etf-cmp__picks-list">
      <li
        v-for="pick in picks"
        :key="pick.code"
        class="etf-cmp__pick"
        :class="{ 'etf-cmp__pick--first': pick.rank === 1 }"
      >
        <!-- 整卡可点进 ETF 详情（与表内名称跳转同一路由惯例）；
             无路由时退化为只读卡片，不给死链 -->
        <component
          :is="pick.route ? RouterLink : 'span'"
          :to="pick.route || undefined"
          class="etf-cmp__pick-link"
        >
          <span class="etf-cmp__pick-rank">
            {{ recommendLabel(pick.rank) }}
          </span>
          <span class="etf-cmp__pick-name" :title="pick.name || pick.code">
            {{ pick.name || pick.code }}
          </span>
          <span class="etf-cmp__pick-meta">
            <span class="etf-cmp__pick-code">{{ pick.code }}</span>
            <span class="etf-cmp__pick-tracking" :title="TRACKING_TITLE">
              <span class="etf-cmp__pick-tracking-label">跟踪差</span>
              <span
                class="etf-cmp__pick-tracking-value"
                :class="pctClass(pick.tracking)"
              >
                {{ trackingText(pick.tracking) }}
              </span>
            </span>
          </span>
        </component>
      </li>
    </ul>
    <p class="etf-cmp__picks-note">按跟踪差（近1年）排序，门槛内取前三。</p>
  </div>
</template>

<style scoped>
/* scoped 说明：小卡内部的每一个 `span` 都是本组件的元素，拿不到父组件的
   scopeId（只有根节点 `.etf-cmp__picks` 能拿到），整套样式必须自带一份。
   第 1 名用品牌软底 + 品牌边框拉开层级，2/3 名为中性小卡——不引入表外新色，
   暗色由 token 自动切换。 */
.etf-cmp__picks {
  margin-bottom: var(--space-3);
}

.etf-cmp__picks-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.etf-cmp__picks-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-2);
  padding: 0;
  margin: 0;
  list-style: none;
}

.etf-cmp__pick {
  min-width: 0;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

/* 第 1 名：品牌软底 + 品牌边框，强调层级明显高于 2/3 名的中性卡 */
.etf-cmp__pick--first {
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.etf-cmp__pick-link {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  color: inherit;
  text-decoration: none;
  border-radius: inherit;

  &:hover {
    background: var(--bg-soft);
  }

  &:focus-visible {
    outline: 2px solid var(--brand-700);
    outline-offset: 2px;
  }
}

.etf-cmp__pick--first .etf-cmp__pick-link:hover {
  background: var(--brand-200);
}

.etf-cmp__pick-rank {
  align-self: flex-start;
  padding: 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 500;
  line-height: 18px;
  color: var(--text-tertiary-ink);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

/* 第 1 名名次标：品牌文字级令牌（--brand-ink，AA 达标），勿用图形级 --brand-700 */
.etf-cmp__pick--first .etf-cmp__pick-rank {
  color: var(--brand-ink);
  border-color: var(--brand-400);
}

.etf-cmp__pick-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.etf-cmp__pick--first .etf-cmp__pick-name {
  font-weight: 600;
}

.etf-cmp__pick-meta {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  min-width: 0;
}

.etf-cmp__pick-code {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.etf-cmp__pick-tracking {
  display: inline-flex;
  gap: var(--space-1);
  align-items: baseline;
  min-width: 0;
}

.etf-cmp__pick-tracking-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.etf-cmp__pick-tracking-value {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.etf-cmp__picks-note {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
