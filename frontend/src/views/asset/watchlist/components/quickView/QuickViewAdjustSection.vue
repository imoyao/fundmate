<script setup lang="ts">
import DrawerSection from "@/components/ProductDrawer/DrawerSection.vue";
import type { AdvisorAdjustGroup } from "@/api/funds";
import { opClassOf, ratioTextOf } from "./quickViewModel";

/**
 * 「成分与调仓」区块（#1468）：抽屉打开时按需拉取，不进列表主请求。
 *
 * `.wqv-row` / `.wqv-adjust` / `.wqv-op*` 是既有 e2e 的定位钩子；样式只保留本区块
 * 独有的调仓明细部分（`.wqv-adjust*` / `.wqv-li*` / `.wqv-op*`），骨架走 `.pd-*`。
 */
defineProps<{
  loading: boolean;
  error: string;
  holdingsCount: number;
  missingCount: number;
  adjustGroups: AdvisorAdjustGroup[];
  /** 且慢平台：官方接口未覆盖时靠快照推导，空态要额外说明（不是故障） */
  isQieman: boolean;
}>();
</script>

<template>
  <DrawerSection title="成分与调仓">
    <p v-if="loading" class="pd-hint">加载中…</p>
    <p v-else-if="error" class="pd-hint">{{ error }}</p>
    <template v-else>
      <dl class="pd-list">
        <div class="pd-row wqv-row">
          <dt class="pd-row__label">成分基金</dt>
          <dd class="pd-row__value">
            <span v-if="holdingsCount">{{ holdingsCount }} 只</span>
            <span v-else>—</span>
            <span v-if="missingCount" class="pd-hint">
              · {{ missingCount }} 只未收录本地
            </span>
          </dd>
        </div>
      </dl>

      <div v-if="adjustGroups.length" class="wqv-adjusts">
        <div v-for="g in adjustGroups" :key="g.adjust_date" class="wqv-adjust">
          <div class="wqv-adjust__head">
            <span class="wqv-adjust__date">{{ g.adjust_date }}</span>
            <span class="pd-hint">{{ g.items.length }} 只调整</span>
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
      <p v-else class="pd-hint">
        暂无调仓记录{{ isQieman ? "（官方未收录时需 2 次快照后推导）" : "" }}
      </p>
    </template>
  </DrawerSection>
</template>

<style scoped lang="scss">
/* 调仓明细：按调仓日分组的紧凑列表 */
.wqv-adjusts {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.wqv-adjust__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-1);
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
  gap: var(--space-2);
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
  margin-right: var(--space-1);
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
