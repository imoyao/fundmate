<script setup lang="ts">
/**
 * 流水线视图的**一行**（流水页重设计 §三 / §五）。
 *
 * 从 `TransactionTimelineView.vue` 拆出（`check_vue_size.mjs` 的 400 行门禁）。拆的
 * 依据不是行数而是职责：视图负责「按月分组 + 折叠 + 触底加载」，这一行负责「一笔
 * 流水怎么读」——三态胶囊、账户胶囊、金额方向、状态声量全在这里，改口径只改一处。
 *
 * ## 两条口径要点
 *
 * - **金额带 ± 但不染色**：± 回答「钱进还是钱出」，不是涨跌。染红绿会把「卖出一笔
 *   换回现金」读成「亏了」，而这个误解在流水页最致命（用户是来对账的）。
 * - **已清仓不打灰**：清仓不是删除。整行灰度会让金额一起变淡，正好毁掉对账要看的数。
 */
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import TransactionAccountCell from "@/components/TransactionTable/TransactionAccountCell.vue";
import {
  CLEARED_BADGE_TITLE,
  positionStateOf,
  statusTone,
  typeClass,
  type TransactionRow
} from "@/components/TransactionTable/model";
import { txnTypeLabel } from "@/constants";
import { formatDate } from "@/utils/date";
import { txnStatusLabel } from "@/utils/transactionStatus";
import { signedAmount, timelineDotClass } from "./transactionListModel";
import type { TransactionRecord } from "@/api/transactions";

const props = defineProps<{ txn: TransactionRecord }>();

const emit = defineEmits<{ edit: [row: TransactionRecord] }>();

/** 账户 / 状态单元格共用 `TransactionRow` 口径（与表格视图完全同一份实现） */
const row = computed<TransactionRow>(() => ({
  ...props.txn,
  symbol: props.txn.symbol ?? undefined
}));

const cleared = computed(() => positionStateOf(row.value) === "cleared");

/** 月内只显示「月-日」：年份已在月头，行内再印一遍是重复信息 */
const dayText = computed(() => {
  const day = formatDate(props.txn.trade_date || props.txn.confirm_date || "");
  return day ? day.slice(5) : "--";
});
</script>

<template>
  <li class="txn-row">
    <span
      class="txn-row__dot"
      :class="timelineDotClass(txn.type)"
      aria-hidden="true"
    />
    <span class="txn-row__date">{{ dayText }}</span>
    <span class="txn-row__type" :class="typeClass(txn.type)">{{
      txnTypeLabel(txn.type) || txn.type
    }}</span>
    <span class="txn-row__asset">
      <span class="txn-row__name">{{ txn.position_name }}</span>
      <span v-if="cleared" class="txn-row__badge" :title="CLEARED_BADGE_TITLE"
        >已清仓</span
      >
      <span v-if="txn.notes" class="txn-row__notes">{{ txn.notes }}</span>
    </span>
    <span class="txn-row__account">
      <TransactionAccountCell :row="row" />
    </span>
    <span class="txn-row__amount">
      <MoneyDisplay :value="signedAmount(txn)" :auto-color="false" size="sm" />
    </span>
    <span class="txn-status" :class="`txn-status--${statusTone(txn.status)}`">{{
      txnStatusLabel(txn.status)
    }}</span>
    <!-- 行内编辑：hover 淡入，键盘 focus 与触屏常驻兜底（与表格同一规范） -->
    <span class="txn-row__edit">
      <el-button text size="small" @click="emit('edit', txn)">编辑</el-button>
    </span>
  </li>
</template>

<style scoped>
/* 7 列固定栅格：圆点 │ 日期 │ 类型 │ 资产 │ 账户 │ 金额 │ 状态
   同一账户的流水上下对齐——扫一眼就是「这个账户最近在干什么」。
   字号按设计 §二 字阶：行内主信息 14/500、元信息 13/400（不引入第四档）。
   行高用 padding 撑出呼吸感，不靠压缩行内信息。 */
.txn-row {
  position: relative;
  display: grid;
  grid-template-columns:
    16px 52px 56px minmax(0, 1fr) minmax(0, 100px)
    108px 56px;
  gap: var(--space-2);
  align-items: center;
  padding: 11px var(--space-compact);
  font-size: var(--text-small);
}

.txn-row:hover {
  background: var(--bg-soft);
}

.txn-row__dot {
  display: inline-flex;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-buy {
  background: var(--color-rise-ink);
}

.dot-sell {
  background: var(--color-fall-ink);
}

.dot-dividend {
  background: var(--color-warning-ink);
}

.dot-deposit {
  background: var(--color-info-ink);
}

.dot-withdraw,
.dot-default {
  background: var(--text-tertiary-ink);
}

.txn-row__date,
.txn-row__notes {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.txn-row__type {
  font-weight: 500;
}

.txn-row__asset {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 6px;
  align-items: baseline;
  min-width: 0;
}

.txn-row__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  white-space: nowrap;
}

/* 已清仓：安静的胶囊（软底 + 次要字色），不是警告色 */
.txn-row__badge {
  padding: 1px 6px;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  background: var(--bg-soft);
  border-radius: var(--radius-xs);
}

.txn-row__account {
  overflow: hidden;
  font-size: var(--text-small);
  white-space: nowrap;
}

.txn-row__amount {
  overflow: hidden;
  text-align: right;
  white-space: nowrap;
}

/* 状态：与表格同一套声量语义（成功静默、只有异常态出声） */
.txn-status {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.txn-status--danger {
  color: var(--color-danger-ink);
}

.txn-status--warning {
  color: var(--color-warning-ink);
}

.txn-status--outline {
  padding: 0 5px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xs);
}

/* 类型色：**-ink 档**（原值作文字 3.86:1 / 2.0:1，白底不达 AA）。
   涨跌色只属于方向列，金额列一律墨色。 */
.txn-type--rise {
  color: var(--color-rise-ink);
}

.txn-type--fall {
  color: var(--color-fall-ink);
}

.txn-type--info {
  color: var(--color-info);
}

/* 行内编辑 hover 淡入（与表格同一规范）：鼠标设备默认隐藏，
   键盘 focus 与触屏常驻兜底（`guard_a11y_interaction` 规则 3）。 */
.txn-row__edit {
  position: absolute;
  top: 50%;
  right: var(--space-compact);
  padding-left: 8px;
  background: linear-gradient(to right, transparent, var(--bg-soft) 20%);
  opacity: 0;
  transform: translateY(-50%);
  transition: opacity 200ms ease-out;
}

.txn-row:hover .txn-row__edit {
  opacity: 1;
}

.txn-row__edit:focus-within {
  opacity: 1;
}

@media (hover: none) {
  .txn-row__edit {
    position: static;
    background: none;
    opacity: 1;
    transform: none;
  }
}
</style>
