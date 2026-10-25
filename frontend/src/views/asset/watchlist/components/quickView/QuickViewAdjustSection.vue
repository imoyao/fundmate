<script setup lang="ts">
import type { AdvisorAdjustGroup } from "@/api/funds";
import { opClassOf, ratioTextOf } from "./quickViewModel";

defineProps<{
  loading: boolean;
  error: string;
  holdingsCount: number;
  missingCount: number;
  adjustGroups: AdvisorAdjustGroup[];
  /** 且慢的调仓靠持仓快照推导，空态要额外说明（不是故障） */
  isQieman: boolean;
}>();
</script>

<template>
  <!-- 投顾组合成分与调仓（#1468）：抽屉打开时按需拉取，不进列表主请求 -->
  <section class="wqv-sec">
    <h4 class="wqv-sec__title">成分与调仓</h4>

    <div v-if="loading" class="wqv-hint">加载中…</div>
    <div v-else-if="error" class="wqv-empty">{{ error }}</div>
    <template v-else>
      <dl class="wqv-list">
        <div class="wqv-row">
          <dt class="wqv-label">成分基金</dt>
          <dd class="wqv-value">
            <span v-if="holdingsCount">{{ holdingsCount }} 只</span>
            <span v-else class="wqv-empty">—</span>
            <span v-if="missingCount" class="wqv-hint">
              · {{ missingCount }} 只未收录本地
            </span>
          </dd>
        </div>
      </dl>

      <div v-if="adjustGroups.length" class="wqv-adjusts">
        <div v-for="g in adjustGroups" :key="g.adjust_date" class="wqv-adjust">
          <div class="wqv-adjust__head">
            <span class="wqv-adjust__date">{{ g.adjust_date }}</span>
            <span class="wqv-hint">{{ g.items.length }} 只调整</span>
          </div>
          <ul class="wqv-adjust__list">
            <li v-for="it in g.items" :key="it.fund_code" class="wqv-li">
              <span class="wqv-li__name" :title="it.fund_name || ''">
                {{ it.fund_name || it.fund_code }}
              </span>
              <span class="wqv-li__ratio">
                <span :class="opClassOf(it.op_name)">{{ it.op_name }}</span>
                {{ ratioTextOf(it) }}
              </span>
            </li>
          </ul>
        </div>
      </div>
      <div v-else class="wqv-empty">
        暂无调仓记录{{ isQieman ? "（需累积 ≥2 次持仓快照后自动推导）" : "" }}
      </div>
    </template>
  </section>
</template>

<style scoped lang="scss">
@use "./wqv-base";

/* 调仓明细：按调仓日分组的紧凑列表 */
.wqv-adjusts {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.wqv-adjust__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 4px;
}

.wqv-adjust__date {
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-primary);
}

.wqv-adjust__list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.wqv-li {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  padding: 2px 0;
  font-size: var(--text-label);
}

.wqv-li__name {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
}

.wqv-li__ratio {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.wqv-op {
  margin-right: 4px;
  color: var(--text-tertiary-ink);
}

/* 加/减仓用涨跌语义变量（不硬编码色值），其余操作保持中性色 */
.wqv-op--add {
  color: var(--color-rise-ink);
}

.wqv-op--cut {
  color: var(--color-fall-ink);
}
</style>
