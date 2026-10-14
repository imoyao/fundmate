<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getFundPerformance, type FundPerformanceResult } from "@/api/products";

/**
 * 详情页「业绩与风险」区块（#2029 卡 B · 设计卡 §4.1 #3）。
 *
 * 取数一次到位：`GET /api/products/fund-performance/` 把区间收益切面、最大回撤、年化波动率
 * 打包返回（后端基于 daily_worth.acc_nav 现算，与自选域同源）。
 *
 * 口径与降级（设计 §6 诚实降级，不编造占位值）：
 * - `fund_kind: "money"`：货币基金没有日涨跌 / 回撤口径，后端改返万份收益 + 七日年化，
 *   本区块只显这两项，不显净值型指标（避免误读「货币也跌了」）；
 * - `applicable: false` / 字段 null：逐项降级为「—」；
 * - 区间收益是**涨跌**，走 RiseFallText（涨红跌绿，与全站一致）；最大回撤 / 波动率
 *   是风险幅度而非方向性涨跌，用中性色，不把「绿」误读成「好」。
 *
 * #167 追加：
 * - **本轮回撤**（`current_drawdown`）是「现在疼不疼」，**最大回撤**是「最疼过多少」——
 *   两个都要显。只显最大值会把「跌 30% 但已修复」与「跌 30% 且仍在水下」显示成一个数，
 *   而后一种正是要警惕的「跌起来比涨得还猛」（#167 用户原话）。
 * - 风险比（夏普 / 索提诺 / 卡玛 / UI / UPI / 波回比）**只在同类内可比**：债基波动天生小、
 *   夏普系统性偏高。故本区块不画排行榜、不给「好/差」色，只把数字与口径摆出来。
 * - rf（无风险利率）与窗口随值下发并展示在脚注——不告诉用户 rf 取多少的夏普不可复核。
 */
const props = defineProps<{
  symbol: string;
}>();

const loading = ref(false);
const perf = ref<FundPerformanceResult | null>(null);
const failed = ref(false);

const DASH = "—";

/** 数值 + 单位，null/undefined 降级「—」（诚实降级：不编造占位值）。 */
function fmtPct(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : v.toFixed(digits) + "%";
}

/** 比值类指标（无量纲）保留 2 位。 */
function fmtRatio(v: number | null | undefined): string {
  return v == null ? DASH : v.toFixed(2);
}

/** 回撤文案：0 说「正在新高」，负数说「跌了多少」——0 与 -0.0 都是「在最高点」。 */
function drawdownText(v: number | null | undefined): string {
  if (v == null) return DASH;
  if (Math.abs(v) < 0.005) return "正在新高";
  return v.toFixed(2) + "%";
}

const PERIOD_LABEL: Record<string, string> = {
  day: "日",
  week: "周",
  month: "月"
};

/** 本轮熬了多久：自然日 → 「3 天 / 2 个月 / 1 年」这类人话，不显裸数字。 */
function daysText(days: number | null | undefined): string {
  if (days == null) return DASH;
  if (days <= 0) return "今天";
  if (days < 60) return `${days} 天`;
  if (days < 365) return `${Math.floor(days / 30)} 个月`;
  const y = Math.floor(days / 365);
  const m = Math.floor((days % 365) / 30);
  return m > 0 ? `${y} 年 ${m} 个月` : `${y} 年`;
}

const riskRows = computed(() => {
  const p = perf.value;
  if (!p || p.fund_kind !== "fund") return [];
  return [
    {
      key: "calmar",
      label: "卡玛比率",
      hint: "年化收益 / 最大回撤",
      value: fmtRatio(p.calmar)
    },
    {
      key: "sortino",
      label: "索提诺",
      hint: "只罚下跌波动",
      value: fmtRatio(p.sortino)
    },
    {
      key: "sharpe",
      label: "夏普",
      hint: `(年化 − rf) / 波动，rf=${(p.risk_free_rate ?? 0) * 100}%`,
      value: fmtRatio(p.sharpe)
    },
    {
      key: "ulcer",
      label: "溃疡指数",
      hint: "整段煎熬的深度（UI）",
      value: fmtPct(p.ulcer_index)
    },
    { key: "upi", label: "UPI", hint: "年化收益 / UI", value: fmtRatio(p.upi) },
    {
      key: "rrd",
      label: "波回比",
      hint: "年化 / (波动 × 最大回撤)",
      value: fmtRatio(p.return_drawdown_ratio)
    }
  ];
});

const hasRiskRows = computed(() => riskRows.value.some(r => r.value !== DASH));

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getFundPerformance(props.symbol);
    perf.value = res.data;
  } catch {
    // 非基金代码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    perf.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="performance-section">
    <SectionHeader title="业绩与风险" />

    <p v-if="loading" class="performance-section__hint">正在读取业绩与风险…</p>

    <p
      v-else-if="failed || !perf || !perf.applicable"
      class="performance-section__hint"
    >
      暂无可展示的业绩数据
    </p>

    <!-- 货币基金：万份收益 + 七日年化（无回撤口径） -->
    <template v-else-if="perf.fund_kind === 'money'">
      <dl class="performance-section__kpi">
        <div class="performance-section__kpi-item">
          <dt class="performance-section__label">七日年化</dt>
          <dd class="performance-section__value">
            {{
              perf.annual_return_7d != null
                ? perf.annual_return_7d.toFixed(2) + "%"
                : DASH
            }}
          </dd>
        </div>
        <div class="performance-section__kpi-item">
          <dt class="performance-section__label">万份收益</dt>
          <dd class="performance-section__value">
            {{
              perf.nav_per_10k != null
                ? perf.nav_per_10k.toFixed(4) + " 元"
                : DASH
            }}
          </dd>
        </div>
      </dl>
      <p class="performance-section__footnote">
        数据来源：{{ perf.source
        }}<template v-if="perf.as_of"> · 截至 {{ perf.as_of }}</template>
        · 货币基金（万份收益 / 七日年化，无回撤口径）
      </p>
    </template>

    <!-- 场外基金：区间收益 + 风险指标 -->
    <template v-else>
      <div class="performance-section__block-label">区间收益</div>
      <dl class="performance-section__facts">
        <div
          v-for="iv in perf.intervals"
          :key="iv.key"
          class="performance-section__fact"
        >
          <dt class="performance-section__label">{{ iv.label }}</dt>
          <dd class="performance-section__value">
            <RiseFallText v-if="iv.value != null" :value="iv.value" />
            <span v-else>{{ DASH }}</span>
          </dd>
        </div>
      </dl>

      <div class="performance-section__block-label">回撤</div>
      <dl class="performance-section__facts">
        <!-- 本轮回撤（#167）：现在疼不疼 —— 与「最大回撤（最疼过多少）」是两个问题 -->
        <div class="performance-section__fact">
          <dt class="performance-section__label">本轮回撤</dt>
          <dd class="performance-section__value">
            {{ drawdownText(perf.current_drawdown) }}
          </dd>
          <dd class="performance-section__sub">
            <template v-if="perf.current_drawdown_peak_date">
              高点 {{ perf.current_drawdown_peak_date }}
            </template>
            <template v-if="perf.current_drawdown_peak_date">
              · 已 {{ daysText(perf.current_drawdown_days) }}
            </template>
          </dd>
        </div>
        <!-- 最大回撤：最疼过多少 -->
        <div class="performance-section__fact">
          <dt class="performance-section__label">
            最大回撤（{{
              perf.max_drawdown_window || perf.risk_window || "近3年"
            }}）
          </dt>
          <dd class="performance-section__value">
            {{ fmtPct(perf.max_drawdown) }}
          </dd>
          <dd
            v-if="perf.max_drawdown_peak_date && perf.max_drawdown_trough_date"
            class="performance-section__sub"
          >
            {{ perf.max_drawdown_peak_date }} →
            {{ perf.max_drawdown_trough_date }}
          </dd>
        </div>
        <div class="performance-section__fact">
          <dt class="performance-section__label">年化波动率（近1年）</dt>
          <dd class="performance-section__value">
            {{ fmtPct(perf.volatility_1y) }}
          </dd>
        </div>
      </dl>

      <!-- 风险比（#167）：只摆数字与口径，不给排序、不着色 —— 跨类别不可比 -->
      <template v-if="hasRiskRows">
        <div class="performance-section__block-label">
          风险比
          <span class="performance-section__aside"
            >{{ perf.risk_window || "近3年" }} · 同类内可比</span
          >
        </div>
        <dl class="performance-section__facts">
          <div
            v-for="row in riskRows"
            :key="row.key"
            class="performance-section__fact"
          >
            <dt class="performance-section__label" :title="row.hint">
              {{ row.label }}
            </dt>
            <dd class="performance-section__value">{{ row.value }}</dd>
          </div>
          <div class="performance-section__fact">
            <dt
              class="performance-section__label"
              :title="`${PERIOD_LABEL[perf.win_rate_period || 'month'] || ''}频；滚动窗口重叠，是持有体验而非概率`"
            >
              胜率（{{
                PERIOD_LABEL[perf.win_rate_period || "month"] || "月"
              }}）
            </dt>
            <dd class="performance-section__value">
              {{ fmtPct(perf.win_rate) }}
            </dd>
          </div>
        </dl>
      </template>

      <p class="performance-section__footnote">
        数据来源：{{ perf.source
        }}<template v-if="perf.as_of"> · 截至 {{ perf.as_of }}</template>
        <template v-if="perf.risk_free_rate != null">
          · rf={{ (perf.risk_free_rate * 100).toFixed(2) }}%</template
        >
        <template v-if="perf.risk_sample_points">
          · 样本 {{ perf.risk_sample_points }} 个净值点</template
        >
        <template v-if="perf.acc_nav_caveat">
          · {{ perf.acc_nav_caveat }}</template
        >
      </p>
      <!-- 口径告警（如检出净值跳变）：与「不可复核的数字」相比，宁可显式说出来 -->
      <p
        v-for="(caveat, i) in perf.risk_caveats || []"
        :key="i"
        class="performance-section__caveat"
      >
        {{ caveat }}
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.performance-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.performance-section__hint,
.performance-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

/* 令牌口径：`--text-secondary` 在 colors.css:33 有定义（`--text-secondary-ink` 未定义，
   写了会让整条 color 声明静默失效 → 回落浏览器默认色，暗色端直接失控）。 */
.performance-section__block-label {
  margin: var(--space-3) 0 var(--space-1);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.performance-section__label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.performance-section__value {
  margin: 0;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 区间收益 / 风险：与基金资料卡同款 facts 网格（#1969 P0，严禁 minmax(0,1fr) 塌轨） */
.performance-section__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.performance-section__fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

/* 标签旁的次要说明（「已 3 个月」「近3年 · 同类内可比」）：12px 三级色，不抢主信息 */
.performance-section__aside {
  margin-left: var(--space-1);
  font-size: 11px;
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

/* 口径副行（高点/低点日期）：比正文再小一档 */
.performance-section__sub {
  margin: 0;
  font-size: 11px;
  color: var(--text-tertiary-ink);
}

/* 口径告警：暖沙金文字级（--color-warning 只许作底/边，禁作前景，见 #1545） */
.performance-section__caveat {
  margin: 0;
  font-size: 12px;
  color: var(--color-warning-ink);
}

/* 货基 KPI：两枚大数字横排 */
.performance-section__kpi {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.performance-section__kpi-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
</style>
