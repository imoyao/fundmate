<template>
  <CardBlock
    class="aggregation-card"
    role="button"
    tabindex="0"
    :aria-label="`查看${title}明细`"
    :style="{ '--accent': `var(${accent})` }"
    @click="emit('open')"
    @keydown.enter="emit('open')"
  >
    <div class="aggregation-card__head">
      <span class="aggregation-card__icon" aria-hidden="true">
        <IconifyIconOffline :icon="icon" />
      </span>
      <div class="aggregation-card__titles">
        <p class="aggregation-card__title">{{ title }}</p>
        <!-- 集合边界（含货币基金 / 含 ETF）必须留在卡片内：用户会拿这里的数去和首页
             同名数字对，两边集合本就不同，不写清就不知道差在哪。 -->
        <p class="aggregation-card__hint">{{ hint }}</p>
      </div>
      <span v-if="share" class="aggregation-card__share"
        >占总资产 {{ share }}</span
      >
    </div>

    <div class="aggregation-card__amount">
      <MoneyDisplay
        :value="amount"
        size="lg"
        :show-sign="false"
        :auto-color="false"
      />
    </div>

    <div class="aggregation-card__foot">
      <p class="aggregation-card__pnl">
        <span>{{ pnlLabel }}</span>
        <template v-if="pnl?.pnl != null">
          <MoneyDisplay :value="pnl.pnl" size="xs" />
          <ValuationSourceBadge
            v-if="pnl.status === 'estimated'"
            :status="pnl.status"
            size="sm"
          />
        </template>
        <span v-else>—</span>
      </p>
      <!-- 整卡就是按钮（role=button + aria-label），此处不再放第二个可聚焦的按钮：
           嵌套交互控件在键盘上要按两次 Tab 才能越过，且焦点环会框在卡片内部。
           文字只作视觉指路，箭头随卡片 hover 右移 2px。 -->
      <span class="aggregation-card__link" aria-hidden="true">
        查看明细
        <IconifyIconOffline icon="ep:arrow-right" />
      </span>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import type { TodayPnlGroup } from "@/api/summary";

defineOptions({ name: "AggregationSummaryCard" });

defineProps<{
  /** 品类名（基金 / 股票）——只写品类，集合边界交给 hint */
  title: string;
  /** 集合边界小字（含货币基金、E 账户份额 / 含 ETF、可转债） */
  hint: string;
  /** 品类市值（元） */
  amount: number;
  /** 当日估值分组行；null = 该品类无可估值持仓，显示「—」而不是 0 */
  pnl: TodayPnlGroup | null;
  /** 当日收益的标签（基金侧必须标「不含货基」） */
  pnlLabel: string;
  /** 占总资产比例，已格式化（"8.5%"）；null = 不可计算，整项不渲染 */
  share: string | null;
  icon: string;
  /** 图标底色取哪个品种色变量（"--asset-cat-fund" 等），不引入新色 */
  accent: string;
}>();

const emit = defineEmits<{ open: [] }>();
</script>

<style lang="scss" scoped>
.aggregation-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  cursor: pointer;
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.aggregation-card:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.aggregation-card:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.aggregation-card__head {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

/* 品类图标：品种色 12% 透明底 + 同色图标，与账户徽标同源（--asset-cat-*），
   不新增色板。图标只是识别锚点，标题仍是主信息，故尺寸压在 36px。 */
.aggregation-card__icon {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  font-size: var(--text-title);
  color: var(--accent, var(--text-secondary));
  background: color-mix(
    in srgb,
    var(--accent, var(--text-secondary)) 12%,
    transparent
  );
  border-radius: var(--radius-md);
}

.aggregation-card__titles {
  flex: 1;
  min-width: 0;
}

.aggregation-card__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  line-height: 22px;
  color: var(--text-primary);
}

.aggregation-card__hint {
  margin: 2px 0 0;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

/* 占比与品类名同一行右端：它回答「这一篮子占我多少」，属于读金额时的上下文，
   不是页脚注释，故不进 foot 行。 */
.aggregation-card__share {
  flex: none;
  padding-top: 2px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.aggregation-card__amount {
  line-height: 1.2;
}

/* foot：当日收益（左）+ 查看明细（右）。一条 --border-subtle 与金额分开，
   两个元素各占一端，卡片底部不再是「右边一个大红按钮」。 */
.aggregation-card__foot {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.aggregation-card__pnl {
  display: flex;
  gap: 6px;
  align-items: baseline;
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.aggregation-card__link {
  display: inline-flex;
  flex: none;
  gap: 2px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-secondary);
  transition:
    color 0.15s ease,
    transform 0.15s ease;
}

.aggregation-card:hover .aggregation-card__link {
  color: var(--brand-ink);
}

.aggregation-card:hover .aggregation-card__link :deep(svg) {
  transform: translateX(2px);
}

@media (prefers-reduced-motion: reduce) {
  .aggregation-card,
  .aggregation-card__link {
    transition: none;
  }

  .aggregation-card:hover {
    transform: none;
  }
}
</style>
