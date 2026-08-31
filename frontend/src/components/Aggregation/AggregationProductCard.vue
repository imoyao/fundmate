<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatQuantity } from "@/utils/format";
import type { AggregationProductGroup, AggregationSource } from "@/api/ledger";

/**
 * 聚合视图产品卡片（#1101 / #1132 共用）。
 *
 * 信息密度设计（对齐用户反馈"卡片太空"）：
 * - 头部：产品名 + 代码 + 副标题（管理人/机构）
 * - 指标区：四格紧凑排列（份额 / 净值 / 市值 / 占比）
 * - 底部元信息行：数据日期 + 多渠道持有提示
 *
 * 两种模式共用同一套模板，仅副标题来源不同：
 * - 'product'：按产品聚合，副标题=基金管理人
 * - 'institution'：按渠道平铺，副标题=销售机构名
 */
defineOptions({ name: "AggregationProductCard" });

const props = withDefaults(
  defineProps<{
    /** 产品模式：传入聚合后的产品组 */
    group?: AggregationProductGroup;
    /** 渠道模式：传入单条来源记录（institution 模式下使用） */
    source?: AggregationSource;
    /** 当前维度 */
    mode?: "product" | "institution";
    /** 参考净值（渠道模式下 source 可能不含此字段，由父组件传入） */
    navYuan?: number | null;
    /** 快照日期 */
    snapshotDate?: string | null;
    /** 总市值（元），用于计算占比；不传则不显示占比 */
    totalYuan?: number | null;
  }>(),
  {
    mode: "product",
    navYuan: null,
    snapshotDate: null,
    totalYuan: null
  }
);

const emit = defineEmits<{
  (e: "select", payload: AggregationProductGroup | AggregationSource): void;
}>();

const isInstitution = computed(() => props.mode === "institution");

const productName = computed(
  () => props.group?.name || props.source?.name || "--"
);
const productCode = computed(
  () => props.group?.symbol || props.source?.symbol || ""
);

/**
 * 副标题。
 * - institution 维度（按渠道分组、组内按账本平铺）：显示**账本名称**，
 *   用于区分同一渠道下的不同账本；销售机构全称较长，改由悬浮提示承载，
 *   避免挤压卡片布局。注意该维度的分组键是销售机构，不是账本。
 * - product 维度：显示基金管理人。
 */
const subtitle = computed(() => {
  if (isInstitution.value) return props.source?.ledger_name || null;
  return props.group?.fund_manager || null;
});
const subtitleIcon = computed(() => (isInstitution.value ? "ep:wallet" : ""));
/** 副标题悬浮提示：institution 模式补充销售机构全称（Alias） */
const subtitleTitle = computed(() => {
  if (isInstitution.value) {
    const org = props.source?.institution_name;
    const alias = props.source?.institution_alias;
    if (org && alias) return `${org}（${alias}）`;
    return org || null;
  }
  return props.group?.fund_manager || null;
});

const shares = computed(() => {
  if (isInstitution.value) return (props.source?.quantity || 0) / 10000;
  return (props.group?.quantity || 0) / 10000;
});

const marketValueYuan = computed(() => {
  if (isInstitution.value) return (props.source?.market_value_cents || 0) / 100;
  return (props.group?.market_value_cents || 0) / 100;
});

const nav = computed(() => {
  if (isInstitution.value) return props.navYuan;
  return props.group?.nav_yuan ?? null;
});

/** 持仓收益率（小数，如 0.079 → 7.90%）；无成本（后端 return_pct 为 null）时显示 -- */
const returnPct = computed<number | null>(() => {
  if (isInstitution.value) return props.source?.return_pct ?? null;
  return props.group?.return_pct ?? null;
});

/** 收益率文本（带正负号，如 "+7.90%"） */
const returnText = computed(() => {
  const v = returnPct.value;
  if (v == null) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
});

/** 收益率胶囊语义：正收益涨色 / 负收益跌色 / 无成本中性 */
const returnClass = computed(() => {
  const v = returnPct.value;
  if (v == null || v === 0) return "return-badge--flat";
  return v > 0 ? "return-badge--positive" : "return-badge--negative";
});

/** 多渠道持有 tooltip 明细（对齐「N 个账户」弱化为图标的诉求） */
const channelTooltip = computed(() => {
  if (isInstitution.value) return "";
  const names = (props.group?.sources ?? [])
    .map(s => s.ledger_name)
    .filter(Boolean);
  const base = `该基金分散在 ${channelCount.value} 个账户持有`;
  return names.length ? `${base}：${names.join("、")}` : base;
});

/** 显示用的快照日期（格式化后） */
const displayDate = computed(() => {
  const d =
    props.snapshotDate ??
    (isInstitution.value
      ? props.source?.snapshot_date
      : props.group?.snapshot_date);
  if (!d) return null;
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[2]}-${m[3]}` : d;
});

/** 多渠道持有提示 */
const multiChannelHint = computed(() => {
  if (isInstitution.value) return false;
  const srcCount = props.group?.sources?.length ?? 0;
  return srcCount > 1;
});
const channelCount = computed(() => props.group?.sources?.length ?? 0);

function handleClick() {
  const payload = isInstitution.value
    ? (props.source as AggregationSource)
    : (props.group as AggregationProductGroup);
  emit("select", payload);
}
</script>

<template>
  <div
    class="product-card"
    role="button"
    tabindex="0"
    @click="handleClick"
    @keydown.enter="handleClick"
  >
    <!-- 头部：名称 + 代码 + 副标题 -->
    <div class="card-head">
      <p class="product-name" :title="productName">
        {{ productName }}
      </p>
      <p class="product-sub">
        <span class="product-code">{{ productCode }}</span>
        <template v-if="subtitle">
          <span class="sub-dot">·</span>
          <IconifyIconOffline
            v-if="subtitleIcon"
            :icon="subtitleIcon"
            class="sub-icon"
          />
          <span class="product-subtitle" :title="subtitleTitle || subtitle">
            {{ subtitle }}
          </span>
        </template>
      </p>
    </div>

    <!-- 主指标行：资产金额（锚点）+ 收益率胶囊（罗列页扫视核心） -->
    <div class="metric-primary">
      <div class="primary-amount">
        <MoneyDisplay
          :value="marketValueYuan"
          size="md"
          :show-sign="false"
          :auto-color="false"
        />
      </div>
      <span class="return-badge" :class="returnClass">{{ returnText }}</span>
    </div>

    <!-- 辅助信息行：份额 / 净值 左右对等分布 -->
    <div class="metric-secondary">
      <span class="secondary-item">
        <span class="secondary-label">份额</span>
        <span class="secondary-value metric--mono">{{
          formatQuantity(shares)
        }}</span>
      </span>
      <span class="secondary-item secondary-item--end">
        <span class="secondary-label">净值</span>
        <span class="secondary-value metric--mono">{{
          nav != null ? nav.toFixed(4) : "--"
        }}</span>
      </span>
    </div>

    <!-- 底部元信息行 -->
    <div class="card-foot">
      <span v-if="displayDate" class="foot-item">
        <IconifyIconOffline icon="ep:calendar" class="foot-icon" />
        {{ displayDate }}
      </span>
      <span v-if="multiChannelHint" class="foot-item foot-hint">
        <el-tooltip :content="channelTooltip" placement="top">
          <span class="foot-channel">
            <IconifyIconOffline icon="ep:wallet" class="foot-icon" />
            {{ channelCount }} 账户
          </span>
        </el-tooltip>
      </span>
    </div>
  </div>
</template>

<style scoped>
/* ── 响应式：小屏保持一致 ── */
@media (width <= 520px) {
  .primary-amount :deep(.money-display) {
    font-size: 17px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .product-card {
    transition: none;
  }

  .product-card:hover {
    transform: none;
  }
}

.product-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
  padding: var(--space-standard, 18px);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease,
    border-color 0.2s ease;
}

.product-card:hover {
  border-color: var(--border-default);
  box-shadow: var(--shadow-overlay, var(--shadow-raised));
  transform: translateY(-2px);
}

.product-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* ── 头部 ── */
.card-head {
  min-width: 0;
}

.product-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.product-sub {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.product-code {
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.sub-dot {
  opacity: 0.6;
}

.sub-icon {
  font-size: 11px;
  opacity: 0.7;
}

.product-subtitle {
  /* 账本名称稍微右移，与代码/图标拉开层次、避免紧贴 */
  margin-left: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 主指标行：资产金额 + 占比（视觉锚点）── */
.metric-primary {
  display: flex;
  gap: 12px;
  align-items: baseline;
  justify-content: space-between;
  padding-top: var(--space-3, 12px);
  border-top: 1px solid var(--border-subtle, var(--border-light));
}

.primary-amount {
  min-width: 0;

  /* 资产金额用品牌强调色，与 Hero 区呼应 */
}

.primary-amount :deep(.money-display) {
  font-size: 19px;
  font-weight: 700;
  color: var(--brand-600, #f06b57) !important;
}

/* 收益率胶囊：涨跌语义走 design.md「收益率标签」规范（涨 brand-100 底 + 跌 #F0F9F2 底） */
.return-badge {
  flex-shrink: 0;
  padding: 2px 10px;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.6;
  border-radius: var(--radius-pill);
}

.return-badge--positive {
  color: var(--color-rise);
  background: var(--brand-100);
}

.return-badge--negative {
  color: #38a354;
  background: #f0f9f2;
}

.return-badge--flat {
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

/* ── 辅助信息行：份额 / 净值 左右对等分布（次级信息，整体弱化）── */
.metric-secondary {
  display: flex;
  gap: var(--space-3, 12px);
  align-items: baseline;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-tertiary);
}

.secondary-item {
  display: inline-flex;
  gap: 4px;
  align-items: baseline;
  min-width: 0;
}

/* 右端项：整体靠右，与左端形成对等 */
.secondary-item--end {
  justify-content: flex-end;
  text-align: right;
}

.secondary-label {
  flex: none;
  font-size: 10px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.secondary-value {
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.metric--mono {
  font-family: var(--font-mono);
}

/* ── 底部元信息行 ── */
.card-foot {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-top: var(--space-2, 8px);
  font-size: 11px;
  color: var(--text-tertiary);
  border-top: 1px solid var(--border-subtle, var(--border-light));
}

.foot-item {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.foot-icon {
  font-size: 11px;
  opacity: 0.6;
}

.foot-hint {
  margin-left: auto;
}

.foot-channel {
  cursor: help;
}
</style>
