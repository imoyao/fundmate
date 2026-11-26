<script setup lang="ts">
import type { AdvisorAdjustGroup } from "@/api/funds";
import { advisorOpTone, advisorRatioText } from "@/utils/advisorAdjust";

/**
 * 主理人调仓明细的**列表渲染**（持仓页在用）。
 *
 * ## 由来
 *
 * 同一批调仓记录原本有两个出口：持仓页「主理人最近调仓」
 * （`positionSection/PositionAdvisorAdjusts`）与投顾组合详情页。此前渲染只写在
 * 持仓页里，详情页要显示就得抄一遍——那是 §2.1「强制复用」明确禁止的形态，而且
 * 抄完必然漂移：一边改了「几只调整」的措辞或比例口径，另一边不会跟着改，而它们是
 * **同一条记录**。
 *
 * ## 现在只剩持仓页一个出口（2026-11 详情页重设计）
 *
 * 详情页的调仓区块改成了**时间轴 + 单节折叠**形态（`AdvisorAdjustEntry`：日期轴点、
 * 加/减计数、理由按实测截断才给按钮），与这里「一组一段、无轴点」的形态不同，两种
 * 布局各自成立，不再强行合并。但**口径仍然唯一**：方向色与比例文案都走
 * `@/utils/advisorAdjust`（`advisorOpTone` / `advisorRatioText`），与自选速览抽屉同源
 * ——这层是必须共享的部分，抄的只是布局。
 *
 * ## 边界：只渲染，不取数、不判定状态
 *
 * 加载中 / 失败 / 空态由宿主表达——持仓页要强调「不是你自己账户的买卖」，详情页要
 * 强调「这条记录是官方还是推导的」，两处原因说明不同。
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
