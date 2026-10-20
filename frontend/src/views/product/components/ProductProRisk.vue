<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  fetchProRisk,
  type ProRiskBias,
  type ProRiskMetrics,
  type ProRiskResult
} from "@/api/products";
import { formatAmount } from "@/utils/currency";
import { biasColorClass } from "@/utils/temperatureFormat";
import { BIAS_HIGH_THRESHOLD } from "@/constants/temperature";
import ProductProEntitlementNotice from "./ProductProEntitlementNotice.vue";
import {
  classifyProPanelFailure,
  type ProPanelFailure
} from "./proEntitlement";

/**
 * Pro 模块二「偏离与风险控制」——风险指标内容（#994 Phase 2）。
 *
 * ## 数据与口径
 *
 * `GET /api/products/pro-risk/` 三块（块级自治，各自 available + reason）：
 *
 * - **BIAS**：既有 bias 引擎（刘晨明 LOGBIAS，EMA20 对数乖离）——与「探索 ·
 *   行业乖离度排行」同一真相源，颜色分级同款 `biasColorClass`；
 * - **波动率 + VaR 95%**：analytics/var.py 历史模拟，序列经详情页 trend 同源
 *   （场外累计净值 / 场内前复权），1Y 窗口，样本 < 60 不出值；
 * - **账户级并示**：持仓市值（模块一 XIRR 同源）× VaR% = 你的最坏单日亏损。
 *
 * 三条已拍板约束（#994 定稿评论，2026-10-08）：
 * 1. **偏离过高时克制提示**：|BIAS| ≥ 5 出风险提示文案，只讲波动风险、
 *    不做买卖建议（信号标签透传引擎原话，不翻译成操作指令）；
 * 2. **不编数字**：块不可用出 reason 说明，账户级无持仓不出 VaR¥——
 *    不拿虚构市值乘出个数；
 * 3. **口径随值下发**：序列口径（basis）/ 样本量 / 数据日期进脚注，
 *    用户换窗口能对上账。
 *
 * 挂载：ProductProSection 在 pro 状态位 `risk.available=true` 时渲染，
 * 挂载即取数；失败只降级本块，不阻塞 Pro 卡内其余内容。失败分两种态
 * （见 `proEntitlement.ts`）：家庭未开通回 `403 + error_code=1007` ⇒ 渲染权益未开通态；
 * 其余（超时 / 5xx）才说「暂时取不到」。
 */
const props = defineProps<{
  /** 产品代码（与状态位同源） */
  symbol: string;
  /** 入口提示品类（透传，决定乖离率品种类型与序列口径） */
  assetType?: string | null;
}>();

const DASH = "—";

const loading = ref(false);
/** 失败态三选一（`none` / `entitlement` / `error`），判据见 `proEntitlement.ts` */
const failure = ref<ProPanelFailure>("none");
const data = ref<ProRiskResult | null>(null);

const bias = computed<ProRiskBias | null>(() => data.value?.bias ?? null);
const risk = computed<ProRiskMetrics | null>(() => data.value?.risk ?? null);
const account = computed(() => data.value?.account ?? null);

const hasPosition = computed(() => account.value?.has_position === true);

/** BIAS 大数（后端是百分比数值，正 = 高于均线） */
const biasText = computed<string>(() => {
  const v = bias.value?.bias;
  if (v == null || !Number.isFinite(v)) return DASH;
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
});

const biasTone = computed<string>(() => {
  const v = bias.value?.bias;
  if (v == null || !Number.isFinite(v)) return "bias-neutral";
  return biasColorClass(v);
});

/** 克制提示（#994：偏离过高时提示波动风险；阈值与引擎同源 5） */
const biasWarning = computed<string | null>(() => {
  const v = bias.value?.bias;
  if (v == null || !Number.isFinite(v)) return null;
  if (Math.abs(v) < BIAS_HIGH_THRESHOLD) return null;
  return "净值明显偏离均线，短期波动风险偏高——注意持有体验，本面板不做买卖建议";
});

/** 风险指标格：年化波动率 / VaR 95% / 日收益样本 */
const riskCells = computed(() => {
  const r = risk.value;
  if (!r) return [];
  return [
    {
      key: "volatility",
      label: "年化波动率",
      value:
        r.annual_volatility == null
          ? DASH
          : `${r.annual_volatility.toFixed(2)}%`
    },
    {
      key: "var",
      label: "VaR 95%（单日）",
      value: r.var_95 == null ? DASH : `${r.var_95.toFixed(2)}%`
    },
    { key: "sample", label: "日收益样本", value: `${r.sample_returns} 个` }
  ];
});

/** 账户级并示：按你的持仓，最坏单日亏多少 */
const accountText = computed<string | null>(() => {
  const a = account.value;
  if (!a?.has_position || a.var_95_yuan == null) return null;
  return `按你的持仓市值 ¥${formatAmount(a.position_value)}，95% 置信下最坏单日约 -¥${formatAmount(
    Math.abs(a.var_95_yuan)
  )}`;
});

const footnote = computed(() => {
  const r = risk.value;
  if (!r) return "";
  const parts: string[] = [];
  if (r.basis) parts.push(r.basis);
  if (r.as_of) parts.push(`数据截至 ${r.as_of}`);
  parts.push(`近${r.window}窗口 · ${r.sample_returns} 个日收益`);
  if (r.caveats.length) parts.push(r.caveats[0]);
  return parts.join(" · ");
});

/** 三块全不可用且无持仓 → 引导文案（不是错误态，也不是权益态） */
const nothingAvailable = computed(() => {
  if (failure.value !== "none" || loading.value) return false;
  return (
    bias.value?.available !== true &&
    risk.value?.available !== true &&
    !hasPosition.value
  );
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failure.value = "none";
  data.value = null;
  try {
    const res = await fetchProRisk(props.symbol, props.assetType);
    data.value = res.data;
  } catch (error) {
    // 权益未开通（403 + error_code=1007）≠ 故障：前者讲边界、后者讲「稍后再试」。
    // 两种态都只降级本块，不阻塞 Pro 卡内其余内容（详情页各区块独立降级）
    failure.value = classifyProPanelFailure(error);
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="pro-risk">
    <p v-if="loading" class="pro-risk__hint">正在计算乖离率与风险指标…</p>

    <ProductProEntitlementNotice
      v-else-if="failure === 'entitlement'"
      subject="风险指标"
    />

    <p v-else-if="failure === 'error'" class="pro-risk__hint">
      风险指标暂时取不到，稍后再来看看
    </p>

    <template v-else-if="!nothingAvailable">
      <!-- BIAS（基金级，既有 bias 引擎口径） -->
      <div v-if="bias?.available" class="pro-risk__bias">
        <div class="pro-risk__bias-head">
          <span class="pro-risk__bias-label">净值乖离率（BIAS）</span>
          <span class="pro-risk__bias-value" :class="biasTone">{{
            biasText
          }}</span>
          <span v-if="bias?.label" class="pro-risk__bias-tag">{{
            bias.label
          }}</span>
          <span
            v-if="bias?.stale"
            class="pro-risk__stale"
            title="行情源暂不可用，基于最近一次成功抓取的价格计算"
            >数据滞后</span
          >
        </div>
        <p v-if="bias?.data_date" class="pro-risk__bias-date">
          净值 {{ bias.close != null ? bias.close.toFixed(4) : DASH }} ·
          数据日期 {{ bias.data_date }}
        </p>
        <p v-if="biasWarning" class="pro-risk__warning">{{ biasWarning }}</p>
      </div>
      <p v-else-if="bias" class="pro-risk__hint">
        乖离率暂不可用：{{ bias.reason }}
      </p>

      <!-- 波动率 + VaR（基金级，analytics/var.py） -->
      <dl v-if="risk?.available" class="pro-risk__grid">
        <div v-for="cell in riskCells" :key="cell.key" class="pro-risk__cell">
          <dt class="pro-risk__label">{{ cell.label }}</dt>
          <dd class="pro-risk__value">{{ cell.value }}</dd>
        </div>
      </dl>
      <p v-else-if="risk" class="pro-risk__hint">
        风险指标暂不可用：{{ risk.reason }}
      </p>

      <!-- 账户级并示：持仓市值 × VaR% -->
      <p v-if="accountText" class="pro-risk__account">{{ accountText }}</p>
      <p v-else-if="!hasPosition" class="pro-risk__hint">
        买入这只标的后，可按你的持仓市值估算 95% 置信下的最坏单日亏损。
      </p>

      <p v-if="footnote" class="pro-risk__footnote">{{ footnote }}</p>
    </template>

    <div v-else class="pro-risk__empty">
      <p class="pro-risk__empty-title">这里将展示乖离率、波动率与 VaR</p>
      <p class="pro-risk__empty-desc">
        基于该标的历史净值计算价格乖离率、年化波动率与 95%
        置信单日最大可能亏损（VaR）；买入后还会按你的持仓市值给出最坏单日亏损金额。
      </p>
    </div>
  </section>
</template>

<style scoped>
.pro-risk {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-3);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-risk__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-risk__bias {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.pro-risk__bias-head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.pro-risk__bias-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-risk__bias-value {
  font-size: var(--text-num-hero);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 乖离率配色与「探索 · 行业乖离度排行」同源：温度文字级令牌（#1837），
   极端档用字重表达而非「浅一点的不可读色」 */
.pro-risk__bias-value.bias-extreme-high,
.pro-risk__bias-value.bias-high {
  color: var(--temp-high-ink);
}

.pro-risk__bias-value.bias-extreme-low,
.pro-risk__bias-value.bias-low {
  color: var(--temp-low-ink);
}

.pro-risk__bias-value.bias-extreme-high,
.pro-risk__bias-value.bias-extreme-low {
  font-weight: 700;
}

.pro-risk__bias-value.bias-neutral {
  color: var(--text-primary);
}

.pro-risk__bias-tag {
  padding: 0 var(--space-1);
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
}

.pro-risk__stale {
  padding: 0 var(--space-1);
  font-size: var(--text-label);
  color: var(--color-warning-ink);
  cursor: help;
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border-radius: 4px;
}

.pro-risk__bias-date {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-risk__warning {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
}

.pro-risk__grid {
  display: grid;

  /* auto-fit + 真实最小列宽：minmax(0, 1fr) 会塌轨逐字竖排（#1969 P0 同款规避） */
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: var(--space-3) var(--space-4);
  margin: 0;
}

.pro-risk__cell {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.pro-risk__label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-risk__value {
  margin: 0;
  font-size: var(--text-num-strong);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.pro-risk__account {
  padding: var(--space-2) var(--space-3);
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-primary);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-risk__footnote {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.pro-risk__empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.pro-risk__empty-title {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-risk__empty-desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
