<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { pricePrecision } from "@/utils/pricePrecision";
import { formatQuantity } from "@/utils/format";
import { dayPnlRate, daysText, pnlRate } from "../productPositionMetrics";
import type { ChannelGroup } from "./positionTypes";
import PositionAccountLink from "./PositionAccountLink.vue";
import { shortDate } from "./positionGrouping";

/**
 * 单账户形态：不进表格，走紧凑指标网格（#980 拆分产物）。
 *
 * 为什么单账户不画表：表格的表头 + 单行 + 与该行完全重复的「合计」行是纯开销，
 * 网格用两行就放得下同样的信息（#2005 的结论）。
 */
const props = defineProps<{
  group: ChannelGroup;
  /**
   * 资产类型。**价格类字段的精度由它决定**（基金/ETF/货币基金 4 位，其余 2 位）——
   * 不传就没有判断依据，只能写死位数，于是股票成本也会被显示成 4 位。
   */
  assetType?: string;
}>();
</script>

<template>
  <div class="product-position__channel">
    <PositionAccountLink
      :name="props.group.name"
      :ledger-id="props.group.ledgerId"
    />
  </div>

  <div class="product-position__grid">
    <!-- 盈亏两项是用户打开这一页真正要看的，字号提一档；其余保持同级 -->
    <div class="metric metric--hero">
      <span class="metric__label">持有盈亏</span>
      <span class="metric__value">
        <MoneyDisplay :value="group.pnl" :precision="2" size="lg" />
      </span>
    </div>
    <div class="metric metric--hero">
      <span class="metric__label">持有盈亏率</span>
      <span class="metric__value">
        <RiseFallText :value="pnlRate(group)" suffix="%" />
      </span>
    </div>
    <!-- 当日盈亏（#2007）：与上面两项同级——它是「今天赚了多少」，不是补充信息。
         无基准时显示「—」而不是 0（0 会被读成「今天没涨没跌」，那是结论不是数据）。 -->
    <div class="metric metric--hero">
      <span class="metric__label">
        当日盈亏
        <span v-if="group.dayBasisDate" class="metric__hint">
          截至 {{ shortDate(group.dayBasisDate) }}
        </span>
      </span>
      <span class="metric__value">
        <MoneyDisplay
          v-if="group.dayPnl != null"
          :value="group.dayPnl"
          :precision="2"
          size="lg"
        />
        <span v-else class="metric__empty">—</span>
      </span>
    </div>
    <div class="metric metric--hero">
      <span class="metric__label">当日盈亏率</span>
      <span class="metric__value">
        <RiseFallText
          v-if="dayPnlRate(group) !== null"
          :value="dayPnlRate(group) ?? 0"
          suffix="%"
        />
        <span v-else class="metric__empty">—</span>
      </span>
    </div>
    <div class="metric">
      <span class="metric__label">持有金额</span>
      <span class="metric__value">
        <MoneyDisplay
          :value="group.marketValue"
          :auto-color="false"
          :show-sign="false"
        />
      </span>
    </div>
    <div class="metric">
      <span class="metric__label">持有份额</span>
      <span class="metric__value">{{ formatQuantity(group.quantity) }}</span>
    </div>
    <div class="metric">
      <span class="metric__label">持仓成本</span>
      <span class="metric__value">
        <MoneyDisplay
          :value="group.cost"
          :auto-color="false"
          :show-sign="false"
        />
      </span>
    </div>
    <div class="metric">
      <span class="metric__label">单位成本</span>
      <span class="metric__value">
        <MoneyDisplay
          :value="group.avgPrice"
          :auto-color="false"
          :show-sign="false"
          :precision="pricePrecision(props.assetType)"
        />
      </span>
    </div>
    <div class="metric">
      <span class="metric__label">持仓天数</span>
      <span class="metric__value">{{ daysText(group.holdingDays) }}</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* ===== 单账户：指标网格 ===== */
.product-position__channel {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  margin-bottom: var(--space-compact);
  font-size: var(--text-label);
}

.product-position__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3) var(--space-compact);
}

/* 断点走单一来源（#1571，`_breakpoints.scss`）：md = 48rem = 768px，
   与模板里的 Tailwind `md:` 前缀同阈值同语义，禁止另写裸 @media。 */
@include bp.above("md") {
  .product-position__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.metric__label {
  font-size: var(--text-label);
  line-height: 1.3;
  color: var(--text-tertiary-ink);
}

.metric__value {
  font-size: var(--text-mono-small);
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

/* 盈亏两项是这一页的核心，字号提一档；不改颜色，颜色仍由 RiseFallText / MoneyDisplay 按语义变量给 */
.metric--hero .metric__value {
  font-size: var(--text-num-strong);
}

/* 当日盈亏的基准日注脚（#2007）：它说明「这个『当日』是哪一天」，属标签的一部分，
   故弱化，不与数值争注意力 */
.metric__hint {
  margin-left: var(--space-1);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 「—」占位统一样式：保持字号但走弱色，避免被读成一个真值 */
.metric__empty {
  color: var(--text-tertiary-ink);
}
</style>
