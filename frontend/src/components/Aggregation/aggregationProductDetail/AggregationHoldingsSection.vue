<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatQuantity } from "@/utils/format";
import type { AggregationProductGroup, AggregationSource } from "@/api/ledger";
import {
  dividendOrManagerText,
  fmtShortDate,
  navText,
  shareFromRaw
} from "./aggregationDetailModel";

/**
 * 持仓信息区：四格信息 + 基金管理人 + 分渠道持仓详情 / 单渠道扩展字段。
 *
 * 多根片段（四格 / 管理人 / 渠道 / 单渠道四个并列节点）：包 wrapper 会改变
 * `.info-grid` 的 `border-bottom` 与 `.channel-section` 的 `margin-top` 相邻关系。
 */
defineOptions({ name: "AggregationHoldingsSection" });

const props = withDefaults(
  defineProps<{
    /** 产品聚合数据 */
    group?: AggregationProductGroup | null;
  }>(),
  {
    group: null
  }
);

/** 汇总份额 */
const totalShares = computed(() => shareFromRaw(props.group?.quantity));
/** 参考净值 */
const nav = computed(() => props.group?.nav_yuan ?? null);
/** 快照日期（= 份额日期） */
const snapshotDate = computed(() => props.group?.snapshot_date ?? null);
/** 净值日期（与快照日期一致，均为导入对账日期） */
const navDate = computed(() => props.group?.snapshot_date ?? null);
/** 管理人 */
const manager = computed(() => props.group?.fund_manager ?? null);
/** 分红方式 */
const dividendPref = computed(() => props.group?.dividend_preference ?? null);
/** 来源列表（分渠道持仓明细的数据源） */
const sources = computed<AggregationSource[]>(() => props.group?.sources ?? []);
/** 是否多渠道持有 */
const multiChannel = computed(() => sources.value.length > 1);

/** 分渠道角标文案：分红方式优先，其次管理人 */
function badgeOf(src: AggregationSource): string {
  return dividendOrManagerText(src);
}
</script>

<template>
  <!-- 四格信息 -->
  <div class="info-grid">
    <div class="info-cell">
      <span class="cell-label">持有份额</span>
      <span class="cell-value">{{ formatQuantity(totalShares) }}</span>
    </div>
    <div class="info-cell">
      <span class="cell-label">份额日期</span>
      <span class="cell-value">{{ fmtShortDate(snapshotDate) }}</span>
    </div>
    <div class="info-cell">
      <span class="cell-label">参考净值</span>
      <span class="cell-value">{{ navText(nav) }}</span>
    </div>
    <div class="info-cell">
      <span class="cell-label">净值日期</span>
      <span class="cell-value">{{ fmtShortDate(navDate) }}</span>
    </div>
  </div>

  <!-- 基金管理人 -->
  <div v-if="manager" class="meta-line">
    <span class="meta-label">基金管理人：</span>
    <span class="meta-value meta-link"
      >{{ manager }}
      <IconifyIconOffline icon="ep:arrow-right" class="link-icon" />
    </span>
  </div>

  <!-- 分渠道持仓详情（核心区块，对齐截图3） -->
  <section v-if="multiChannel" class="channel-section">
    <h4 class="section-title">分渠道持仓详情</h4>
    <div class="channel-list">
      <div
        v-for="(src, idx) in sources"
        :key="`${src.ledger_id}-${idx}`"
        class="channel-row"
      >
        <div class="channel-head">
          <IconifyIconOffline icon="ep:wallet" class="channel-icon" />
          <div class="channel-title">
            <!-- 销售机构：AMAC 权威全称（真实完整）；别名为辅助提示 -->
            <span class="channel-name" :title="src.institution_name || ''">
              {{ src.institution_name || "未关联机构" }}
            </span>
            <!-- 对应账本名称 -->
            <span v-if="src.ledger_name" class="channel-ledger">
              <IconifyIconOffline icon="ep:wallet" class="ledger-icon" />
              {{ src.ledger_name }}
            </span>
          </div>
          <span v-if="src.fund_manager" class="channel-dividend">
            {{ badgeOf(src) }}
          </span>
        </div>
        <div class="channel-metrics">
          <span class="ch-shares">{{
            formatQuantity(shareFromRaw(src.quantity))
          }}</span>
          <MoneyDisplay
            :value="(src.market_value_cents || 0) / 100"
            size="sm"
            :show-sign="false"
            :auto-color="false"
          />
        </div>
      </div>
    </div>
  </section>

  <!-- 单渠道时展示该渠道的详细信息（对齐截图4的扩展字段） -->
  <section v-else-if="sources.length === 1" class="single-channel-info">
    <div class="meta-line">
      <IconifyIconOffline icon="ep:wallet" class="meta-icon" />
      <span class="meta-label">销售机构：</span>
      <span class="meta-value">
        {{ sources[0].institution_name || "未关联机构" }}
        <span v-if="sources[0].institution_alias" class="meta-alias">
          ({{ sources[0].institution_alias }})
        </span>
      </span>
    </div>
    <div v-if="sources[0].ledger_name" class="meta-line">
      <IconifyIconOffline icon="ep:wallet" class="meta-icon" />
      <span class="meta-label">账本名称：</span>
      <span class="meta-value">{{ sources[0].ledger_name }}</span>
    </div>
    <div v-if="dividendPref" class="meta-line">
      <span class="meta-label">分红方式：</span>
      <span class="meta-value">{{ dividendPref }}</span>
    </div>
    <div v-if="sources[0].fund_account" class="meta-line">
      <span class="meta-label">基金账户：</span>
      <span class="meta-value mono">{{ sources[0].fund_account }}</span>
    </div>
    <div v-if="sources[0].trade_account" class="meta-line">
      <span class="meta-label">交易账户：</span>
      <span class="meta-value mono">{{ sources[0].trade_account }}</span>
    </div>
  </section>
</template>

<style scoped>
/* ── 四格信息 ── */
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-compact);
  padding: var(--space-5, 24px) 0;
  border-bottom: 1px solid var(--border-light);
}

.info-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cell-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.cell-value {
  font-family: var(--font-mono);
  font-size: var(--text-num-strong);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* ── 元信息行 ── */
.meta-line {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: var(--space-3, 12px) 0;
  font-size: var(--text-small);
}

.meta-icon {
  flex: none;
  font-size: var(--text-small);
  color: var(--brand-500, #f69988);

  /* 与文字基线对齐（图标为 inline-block，需手动微调） */
  transform: translateY(1px);
}

.meta-label {
  flex: none;
  color: var(--text-secondary);
}

.meta-value {
  min-width: 0;
  color: var(--text-primary);
  word-break: break-word;
}

/* 机构别名：辅助提示，弱化显示 */
.meta-alias {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.meta-link {
  color: var(--brand-600, #f06b57);
  cursor: pointer;
}

.link-icon {
  font-size: var(--text-label);
  vertical-align: middle;
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--text-label);
}

/* ── 分渠道持仓详情 ── */
.channel-section {
  margin-top: var(--space-compact);
}

.section-title {
  margin-bottom: var(--space-3, 12px);
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.channel-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
}

.channel-row {
  padding: var(--space-3, 12px);
  background: var(--bg-soft, var(--bg-page));
  border-radius: var(--radius-md);
}

.channel-head {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 8px;
}

.channel-icon {
  flex: none;
  margin-top: 1px;
  font-size: var(--text-small);
  color: var(--brand-500, #f69988);
}

/* 机构全称 + 账本名 竖排 */
.channel-title {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.channel-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-primary);
  word-break: break-word;
}

.channel-ledger {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.ledger-icon {
  flex: none;
  font-size: var(--text-label);
  opacity: 0.65;
}

.channel-dividend {
  flex: none;
  padding: 2px 8px;
  margin-left: auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  background: var(--bg-card);
  border-radius: var(--radius-sm);
}

.channel-metrics {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-left: 22px; /* 与图标对齐 */
}

.ch-shares {
  font-family: var(--font-mono);
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* ── 单渠道扩展信息 ── */
.single-channel-info {
  /* 不再加 border-top：上方 .info-grid 已有 border-bottom，
     重复加会呈现「两条分割线」的观感 */
  padding-top: var(--space-2, 8px);
  margin-top: var(--space-compact);
}
</style>
