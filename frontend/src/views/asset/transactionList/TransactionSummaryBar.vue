<script setup lang="ts">
/**
 * 汇总条（设计 §二 第二带 / §四 口径）：一行读完「这段时间发生了什么」。
 *
 * 只做展示：数字全部来自后端 `GET /api/transactions/summary/`，这里**不求和**。
 * 前端一旦二次求和，就会出现两套口径——本仓已经有过「已实现盈亏两套算法互相矛盾」
 * 的先例，聚合数字只能有一个出处。
 */
import { computed } from "vue";
import type { TransactionSummary } from "@/api/transactions";
import { formatAmount } from "@/utils/currency";

const props = defineProps<{
  /** 后端汇总结果；`null` = 还没取到（此时**整块不渲染**，见模板注释） */
  summary: TransactionSummary | null;
  /** 范围文案：「近一年」/「2026-01-01 至 2026-06-30」，由页面按筛选生成 */
  label: string;
  /** 正在按新筛选重取：保留旧数字 + 降透明度，不闪成空白 */
  loading?: boolean;
}>();

function money(value: number): string {
  return `¥${formatAmount(Number(value) || 0)}`;
}

/** 净投入必须带符号：正数＝净投入，负数＝净取出，两者是相反的事，不能都印成正数 */
function signedMoney(value: number): string {
  const amount = Number(value) || 0;
  return `${amount < 0 ? "-" : "+"}¥${formatAmount(Math.abs(amount))}`;
}

interface SummaryItem {
  key: string;
  value: string;
  count: number | null;
  /** 悬停说明：这些数字都能在表格里逐笔核出来，说明口径就是为了让人核 */
  title: string;
  emphasized?: boolean;
}

const items = computed<SummaryItem[]>(() => {
  const s = props.summary;
  if (!s) return [];
  return [
    {
      key: "买入",
      value: money(s.buy.amount),
      count: s.buy.count,
      title: "成交额，不含手续费（手续费单独一行）"
    },
    {
      key: "卖出",
      value: money(s.sell.amount),
      count: s.sell.count,
      title: "成交额，不含手续费"
    },
    {
      key: "分红",
      value: money(s.dividend.amount),
      count: s.dividend.count,
      title: "现金分红入账合计"
    },
    {
      key: "手续费",
      value: money(s.fee),
      count: null,
      title: "全部类型的费用合计，不摊进买入金额"
    },
    {
      key: "净投入",
      value: signedMoney(s.net_invested),
      count: null,
      title: "买入 + 手续费 − 卖出 − 分红；正数＝净投入，负数＝净取出",
      emphasized: true
    }
  ];
});
</script>

<template>
  <!-- 未取到数据时整块不渲染（设计 §十二-1）：留个空容器比不显示更糟——用户会以为
       这里坏了，而它只是接口还没回来。 -->
  <section
    v-if="summary"
    class="txn-summary"
    :class="{ 'txn-summary--refreshing': loading }"
    :aria-busy="loading ? 'true' : undefined"
    aria-label="交易汇总"
  >
    <p class="txn-summary__range">{{ label }}</p>
    <ul class="txn-summary__cards">
      <li
        v-for="item in items"
        :key="item.key"
        class="txn-summary__card"
        :class="{ 'txn-summary__card--emphasized': item.emphasized }"
        :title="item.title"
      >
        <span class="txn-summary__key">{{ item.key }}</span>
        <span class="txn-summary__value">{{ item.value }}</span>
        <span v-if="item.count !== null" class="txn-summary__count">
          {{ item.count }} 笔
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
/* 卡片式汇总：数字从「一行 13px 小字」升级为「每张卡一个 hero 数字」，
   让「这段时间发生了什么」一眼可读（设计 §二 第二带）。
   仍不求和——数字全部来自后端 `GET /api/transactions/summary/`。 */
.txn-summary {
  padding: var(--space-3) 0;
  transition: opacity 0.15s ease;
}

.txn-summary--refreshing {
  opacity: 0.55;
}

.txn-summary__range {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 自适应卡片网格：宽屏一排 5 张，窄屏自动换行。gap 用 space-2 保持紧凑。 */
.txn-summary__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: var(--space-2);
  padding: 0;
  margin: 0;
  list-style: none;
}

.txn-summary__card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px var(--space-3);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.txn-summary__key {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* hero 数字：等宽 + tabular-nums 保证右对齐对齐，18px（--text-num-strong「指标网格值」
   档）比正文跳一档。字阶一律走令牌——手写 px 即第 N 种自造档位（#2323）。 */
.txn-summary__value {
  font-family: var(--font-mono);
  font-size: var(--text-num-strong);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: var(--text-primary);
}

.txn-summary__count {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 净投入是唯一的结论数字：用主色左侧 accent + 主色字，把它从一排里拎出来。
   不染红绿——金额只回答「进/出」，涨跌色留给方向列（与流水页口径一致）。 */
.txn-summary__card--emphasized {
  background: var(--color-primary-10);
  border-color: var(--color-primary-ink);
}

.txn-summary__card--emphasized .txn-summary__key {
  color: var(--color-primary-ink);
}

.txn-summary__card--emphasized .txn-summary__value {
  font-weight: 700;
  color: var(--color-primary-ink);
}
</style>
