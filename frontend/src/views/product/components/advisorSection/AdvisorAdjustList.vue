<script setup lang="ts">
import type { AdvisorAdjustGroup } from "@/api/funds";
import { advisorOpTone, advisorRatioText } from "@/utils/advisorAdjust";

/**
 * 主理人调仓明细的**列表渲染**（唯一实现）。
 *
 * ## 为什么要单独拆一个组件
 *
 * 同一批调仓记录现在有两个出口：持仓页「主理人最近调仓」
 * （`positionSection/PositionAdvisorAdjusts`）与投顾组合详情页
 * （`advisorSection/AdvisorAdjusts`）。此前渲染只写在持仓页里，详情页要显示就得
 * 抄一遍——那是 §2.1「强制复用」明确禁止的形态，而且抄完必然漂移：
 * 一边改了「几只调整」的措辞或比例口径，另一边不会跟着改，而它们是**同一条记录**。
 *
 * ## 边界：只渲染，不取数、不判定状态
 *
 * 加载中 / 失败 / 空态由宿主各自表达——两处的**原因说明不同**：
 * 持仓页要强调「不是你自己账户的买卖」，详情页要强调「且慢没有官方调仓公告」。
 * 把它塞进本组件就只能写一份，逼出「两边都不太对」的折中。
 *
 * 比例文案与方向色走 `@/utils/advisorAdjust`，与自选速览抽屉同源。
 */
defineProps<{
  /** 按调仓日倒序的分组（后端已排好序，本组件不再排序） */
  groups: AdvisorAdjustGroup[];
}>();
</script>

<template>
  <div class="advisor-adjusts__list">
    <div
      v-for="group in groups"
      :key="group.adjust_date"
      class="advisor-adjusts__group"
    >
      <div class="advisor-adjusts__head">
        <span class="advisor-adjusts__date">{{ group.adjust_date }}</span>
        <span class="advisor-adjusts__count">
          {{ group.items.length }} 只调整
        </span>
      </div>
      <p v-if="group.reason" class="advisor-adjusts__reason">
        {{ group.reason }}
      </p>
      <ul class="advisor-adjusts__items">
        <li
          v-for="item in group.items"
          :key="`${group.adjust_date}-${item.fund_code}`"
          class="advisor-adjusts__item"
        >
          <span
            class="advisor-adjusts__name"
            :title="item.fund_name || item.fund_code"
          >
            {{ item.fund_name || item.fund_code }}
          </span>
          <span class="advisor-adjusts__ratio">
            <span
              class="advisor-adjusts__op"
              :class="`advisor-adjusts__op--${advisorOpTone(item.op_name)}`"
            >
              {{ item.op_name || "调整" }}
            </span>
            {{ advisorRatioText(item) }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.advisor-adjusts__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.advisor-adjusts__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-1);
}

.advisor-adjusts__date {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.advisor-adjusts__count {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 主理人的调仓说明（原文，不做截断——理由短，截断反而看不懂） */
.advisor-adjusts__reason {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.advisor-adjusts__items {
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-adjusts__item {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  padding: 2px 0;
  font-size: var(--text-label);
}

.advisor-adjusts__name {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
}

.advisor-adjusts__ratio {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.advisor-adjusts__op {
  margin-right: var(--space-1);
}

/* 加仓/减仓用涨跌语义变量（不硬编码色值），其余操作保持中性 */
.advisor-adjusts__op--add {
  color: var(--color-rise-ink);
}

.advisor-adjusts__op--cut {
  color: var(--color-fall-ink);
}
</style>
