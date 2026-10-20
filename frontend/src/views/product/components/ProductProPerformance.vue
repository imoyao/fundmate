<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  fetchProInsight,
  type ProInsightBehavior,
  type ProInsightResult,
  type ProInsightXirr
} from "@/api/products";
import { formatAmount } from "@/utils/currency";

/**
 * Pro 模块一「深度绩效与归因」——账户级指标内容（#994 Phase 2）。
 *
 * ## 数据与口径
 *
 * `GET /api/products/pro-insight/`：聚合产品级 XIRR（#1972，资金加权年化，
 * 跨账户现金流合并 + 当前市值虚拟卖出）与交易行为画像（analytics/behavior，
 * FIFO 配对自算盈亏——不读 realized_pnl，存量库该列全 0 与真零盈亏不可区分）。
 *
 * - **账户级是差异化锚**：所有指标来自用户自己的持仓与流水，与基金级口径正交
 *   （#1986「永不退役项」）；
 * - `has_account_data=false` → 渲染引导文案（还不是错误：没买过就没有数据）；
 * - 指标 null → 「—」不编数；平仓样本量 / 未配对排除数进脚注（口径透明）。
 *
 * 挂载：ProductProSection 在 pro 状态位 `performance.available=true` 时渲染，
 * 挂载即取数；接口失败整块降级，不阻塞 Pro 卡内其余内容。
 */
const props = defineProps<{
  /** 产品代码（与状态位同源，后端按 symbol_scope 收敛流水） */
  symbol: string;
  /** 入口提示品类（仅透传回显，不参与判定） */
  assetType?: string | null;
}>();

const DASH = "—";

const loading = ref(false);
const failed = ref(false);
const data = ref<ProInsightResult | null>(null);

const xirr = computed<ProInsightXirr | null>(() => data.value?.xirr ?? null);
const behavior = computed<ProInsightBehavior | null>(
  () => data.value?.behavior ?? null
);

const hasData = computed(() => data.value?.has_account_data === true);

/** XIRR 后端是小数（0.20 = +20%）→ 展示层转百分比 */
const xirrPct = computed<number | null>(() => {
  const v = xirr.value?.xirr;
  if (v == null || !Number.isFinite(v)) return null;
  return v * 100;
});

const metrics = computed(() => {
  const b = behavior.value;
  if (!b) return [];
  return [
    {
      key: "win_rate",
      label: "平仓胜率",
      value: pctText(b.win_rate),
      tone: "plain"
    },
    {
      key: "pl_ratio",
      label: "盈亏比",
      value:
        b.profit_loss_ratio == null
          ? DASH
          : `${b.profit_loss_ratio.toFixed(2)} 倍`,
      tone: "plain"
    },
    {
      key: "holding",
      label: "平均持有天数",
      value:
        b.avg_holding_days == null
          ? DASH
          : `${b.avg_holding_days.toFixed(0)} 天`,
      tone: "plain"
    },
    {
      key: "closed",
      label: "平仓笔数",
      value: `${b.closed_count}`,
      tone: "plain"
    }
  ];
});

const amounts = computed(() => {
  const x = xirr.value;
  const b = behavior.value;
  if (!x || !b) return [];
  return [
    {
      key: "invested",
      label: "总投入",
      value: money(x.total_invested),
      tone: "plain"
    },
    {
      key: "current",
      label: "当前市值",
      value: money(x.current_value),
      tone: "plain"
    },
    {
      key: "total_return",
      label: "累计收益",
      value: signedMoney(x.total_return),
      tone: toneClass(x.total_return)
    },
    {
      key: "realized",
      label: "已实现盈亏",
      value:
        b.realized_pnl_total == null ? DASH : signedMoney(b.realized_pnl_total),
      tone:
        b.realized_pnl_total == null ? "plain" : toneClass(b.realized_pnl_total)
    },
    {
      key: "dividend",
      label: "现金分红",
      value:
        b.cash_dividend_total == null ? DASH : money(b.cash_dividend_total),
      tone: "plain"
    }
  ];
});

const footnote = computed(() => {
  const b = behavior.value;
  if (!b) return "";
  const parts = ["账户级口径 · 基于你自己的持仓与流水 · 盈亏按 FIFO 配对自算"];
  parts.push(`平仓样本 ${b.closed_count} 笔`);
  if (b.unmatched_sell_count > 0) {
    parts.push(`${b.unmatched_sell_count} 笔未配对卖出已诚实排除`);
  }
  return parts.join(" · ");
});

function money(value: number): string {
  return `¥${formatAmount(value)}`;
}

function signedMoney(value: number): string {
  return `${value > 0 ? "+" : ""}¥${formatAmount(Math.abs(value))}`;
}

function pctText(value: number | null): string {
  return value == null ? DASH : `${value.toFixed(2)}%`;
}

/** 红涨绿跌（中国市场惯例）：收益/盈亏按符号着色 */
function toneClass(value: number | null): string {
  if (value == null || value === 0) return "plain";
  return value > 0 ? "rise" : "fall";
}

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    const res = await fetchProInsight(props.symbol, props.assetType);
    data.value = res.data;
  } catch {
    // 接口失败：整块降级，不阻塞 Pro 卡内其余内容（详情页各区块独立降级）
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="pro-perf">
    <p v-if="loading" class="section-footnote">正在计算你的账户级指标…</p>

    <p v-else-if="failed" class="section-footnote">
      账户级指标暂时取不到，稍后再来看看
    </p>

    <template v-else-if="hasData">
      <div class="pro-perf__xirr">
        <span class="pro-perf__xirr-label">持有年化（XIRR）</span>
        <span class="pro-perf__xirr-value" :class="toneClass(xirrPct)">
          {{
            xirrPct == null
              ? DASH
              : `${xirrPct > 0 ? "+" : ""}${xirrPct.toFixed(2)}%`
          }}
        </span>
        <span class="pro-perf__xirr-note">资金加权 · 含你的加减仓时点</span>
      </div>

      <!-- 九项指标合并为一个网格（#2314）：原先是两个独立 dl + auto-fit，
           第二行 4 项会把空轨塌缩后重新均分成 4 列，与第一行 5 列完全错位。
           固定 5 列后两行严格对齐；窄屏（<768px）降为 2 列，见下方断点。 -->
      <dl class="pro-perf__grid">
        <div
          v-for="cell in [...amounts, ...metrics]"
          :key="cell.key"
          class="pro-perf__cell"
        >
          <dt class="pro-perf__label">{{ cell.label }}</dt>
          <dd class="pro-perf__value" :class="`pro-perf__value--${cell.tone}`">
            {{ cell.value }}
          </dd>
        </div>
      </dl>

      <p class="section-footnote">{{ footnote }}</p>
    </template>

    <div v-else class="pro-perf__empty">
      <p class="pro-perf__empty-title">这里将展示你的账户级指标</p>
      <p class="pro-perf__empty-desc">
        买入这只标的后，持有年化（XIRR）、平仓胜率、平均持有天数等会基于你自己的真实流水计算。
      </p>
    </div>
  </section>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

.pro-perf {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-3);

  /* #2314：--bg-muted 是冷灰蓝（#f5f7fa），与暖奶油页面底（#fdfbf7）和
     规范柔和表面 --bg-soft（#f5f0eb）都不搭，是面板「冷一块」的来源 */
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-perf__xirr {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.pro-perf__xirr-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-perf__xirr-value {
  font-size: var(--text-num-hero);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.pro-perf__xirr-value--rise {
  /* #2314：文字色统一 -ink 文字级令牌（图形级 --color-rise 禁作前景文字，design.md:131） */
  color: var(--color-rise-ink);
}

.pro-perf__xirr-value--fall {
  color: var(--color-fall-ink);
}

.pro-perf__xirr-note {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* #2314：固定 5 列（不再 auto-fit 塌轨）+ 真实最小列宽。
   minmax(0, 1fr) 在 auto-fit 下会塌到几像素逐字竖排（#1969 P0），
   固定列数 + 上限断点规避；窄屏降 2 列。 */
.pro-perf__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3) var(--space-4);
  margin: 0;

  @include bp.below("md") {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.pro-perf__cell {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.pro-perf__label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-perf__value {
  margin: 0;

  /* #2314：数字强调三档的 strong 档（18px/600），替换原 15px/400——
      与 12px 标签只差 3px 且无字重区分，数字层次立不住 */
  font-size: var(--text-num-strong);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.pro-perf__value--rise {
  color: var(--color-rise-ink);
}

.pro-perf__value--fall {
  color: var(--color-fall-ink);
}

.pro-perf__empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.pro-perf__empty-title {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-perf__empty-desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
