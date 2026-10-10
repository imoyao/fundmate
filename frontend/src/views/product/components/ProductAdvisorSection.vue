<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getAdvisorProfile, type AdvisorProfileResult } from "@/api/products";
import { getAdvisorHoldings, type AdvisorHoldingsResult } from "@/api/funds";
import { getAdvisorPlatformLabel } from "@/constants/advisorPlatform";
import { productRoute } from "@/utils/productIdentity";

/**
 * 详情页「投顾组合」区块（#1975 · 设计 §6 三期货品）。
 *
 * ## 取数
 *
 * - `GET /api/products/advisor-profile/`（本卡新增）：组合档案 + 可得指标。
 *   此前 `advisor_portfolios` 的档案字段**没有任何端点返回** —— funds 域只有
 *   `advisors/<code>/holdings/` 与 `/adjusts/`，它们回答「持什么、调过什么」，
 *   回答不了「这是个什么组合」，而详情页首屏要的正是后者；
 * - 成分基金复用**已上线**的 `getAdvisorHoldings`，不重写取数链路。
 *
 * ## 内容边界（本次刻意不做调仓记录）
 *
 * 调仓明细（`getAdvisorAdjusts`）**不在本区块渲染**：设计 §7 已把「投顾成分与调仓」
 * 登记为「抽屉既有 + 详情页复用同一组件」，而那需要先把速览抽屉里那段渲染提取成
 * 共用组件（属 B6「速览抽屉是否瘦身」的复评范围）。此处先给**档案 + 指标 + 成分**，
 * 避免同一份渲染逻辑写两遍（§2.1「强制复用」）。
 *
 * ## 降级（设计 §6 诚实降级，不用 mock）
 *
 * 本机真实库 105 个组合实测：`org_name` / `risk_level` / 区间收益 / 回撤 / 波动率 /
 * 夏普填充率 91~100%，这些是区块主体；而 `strategy_type` / `cum_return` /
 * `running_days` / `benchmark` / `excess_return` 为 **0%**、`host` **1.9%**、
 * `return_ytd` **2.9%** —— 一律显示「—」；指标区**只渲染有值的项**，不让一排
 * 「—」占满版面（那是「没数据」的另一种噪声）。
 *
 * ## 不展示代码（设计 §2.6）
 *
 * 组合类标的靠「名称 + 平台 + 机构」识别。⚠️ 注意：设计要求写的是「平台/主理人」，
 * 但主理人实测填充率只有 1.9%，故实际锚点落在**机构**（100%）上 —— 不为凑条文编造。
 */
const props = defineProps<{
  /** 平台组合码（`advisor_portfolios.code`，如 ZH012926 / XCOVSEX） */
  code: string;
}>();

const DASH = "—";

const loading = ref(false);
const failed = ref(false);
const profile = ref<AdvisorProfileResult | null>(null);
const holdings = ref<AdvisorHoldingsResult | null>(null);

const platformLabel = computed(() =>
  profile.value ? getAdvisorPlatformLabel(profile.value.platform) : ""
);

/** 收益指标：只保留有值的项（后端 0% 填充字段恒为 null，不占版面） */
const returnMetrics = computed(() => {
  const p = profile.value;
  if (!p) return [];
  return [
    { label: "近 1 月", value: p.return_1m },
    { label: "近 3 月", value: p.return_1q },
    { label: "近 6 月", value: p.return_6m },
    { label: "近 1 年", value: p.return_1y },
    { label: "成立以来", value: p.return_since_incep },
    { label: "年化", value: p.annual_return }
  ].filter(m => m.value != null);
});

/**
 * 风险指标：与收益分开渲染，且**不用涨跌色** —— 回撤是负数，套用「跌」的绿色
 * 会读成「亏得少」，与语义不符（数字本身带负号已足够）。
 */
const riskMetrics = computed(() => {
  const p = profile.value;
  if (!p) return [];
  const items: Array<{ label: string; text: string | null }> = [
    {
      label: "最大回撤",
      text: p.max_drawdown != null ? `${p.max_drawdown.toFixed(2)}%` : null
    },
    {
      label: "年化波动率",
      text: p.volatility != null ? `${p.volatility.toFixed(2)}%` : null
    },
    {
      label: "夏普比率",
      text: p.sharpe_ratio != null ? p.sharpe_ratio.toFixed(3) : null
    }
  ];
  return items.filter(i => i.text != null);
});

/** 策略说明：摘要与详情都可能有，优先摘要（更短） */
const strategyText = computed(
  () => profile.value?.strategy_summary || profile.value?.strategy_desc || ""
);

function fmtPct(value: number | null): string {
  if (value == null) return DASH;
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function riseFallClass(value: number | null): string {
  if (value == null || value === 0) return "";
  return value > 0 ? "is-rise" : "is-fall";
}

async function load() {
  if (!props.code) return;
  loading.value = true;
  failed.value = false;
  profile.value = null;
  holdings.value = null;
  try {
    const res = await getAdvisorProfile({ code: props.code });
    profile.value = res.data;
  } catch {
    // 未收录 / 网络异常：整块降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
    loading.value = false;
    return;
  }

  // 成分基金只在后端报了条数时才取：多数组合有持仓（103/105），但空组合不该白发请求
  if (profile.value && profile.value.holding_count > 0) {
    try {
      const res = await getAdvisorHoldings(props.code);
      holdings.value = res.data;
    } catch {
      // 成分取不到只影响这一块，上面的档案照常展示
      holdings.value = null;
    }
  }
  loading.value = false;
}

watch(() => props.code, load, { immediate: true });
</script>

<template>
  <CardBlock class="advisor-section">
    <SectionHeader title="投顾组合" />

    <p v-if="loading" class="advisor-section__hint">正在读取投顾组合资料…</p>

    <p v-else-if="failed || !profile" class="advisor-section__hint">
      暂无可展示的投顾组合资料
    </p>

    <template v-else>
      <!-- 识别信息：不展示代码（设计 §2.6），靠名称 + 平台 + 机构 -->
      <dl class="advisor-section__facts">
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">组合名称</dt>
          <dd class="advisor-section__value advisor-section__value--strong">
            {{ profile.name || DASH }}
          </dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">平台</dt>
          <dd class="advisor-section__value">{{ platformLabel || DASH }}</dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">机构</dt>
          <dd class="advisor-section__value advisor-section__value--wrap">
            {{ profile.org_name || DASH }}
          </dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">主理人</dt>
          <dd class="advisor-section__value">{{ profile.host || DASH }}</dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">风险等级</dt>
          <dd class="advisor-section__value">
            {{ profile.risk_level || DASH }}
          </dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">产品类型</dt>
          <dd class="advisor-section__value">
            {{ profile.product_type || DASH }}
          </dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">成立日期</dt>
          <dd class="advisor-section__value">
            {{ profile.estab_date || DASH }}
          </dd>
        </div>
        <div class="advisor-section__fact">
          <dt class="advisor-section__label">最新净值</dt>
          <dd class="advisor-section__value">
            <template v-if="profile.nav != null">
              {{ profile.nav.toFixed(4) }}
            </template>
            <template v-else>{{ DASH }}</template>
            <span v-if="profile.nav_date" class="advisor-section__sub">
              （{{ profile.nav_date }}）
            </span>
          </dd>
        </div>
      </dl>

      <!-- 指标区只渲染有值的项：一排「—」是「没数据」的另一种噪声 -->
      <div v-if="returnMetrics.length" class="advisor-section__metrics">
        <h4 class="advisor-section__metrics-title">收益表现</h4>
        <ul class="advisor-section__metrics-list">
          <li
            v-for="m in returnMetrics"
            :key="m.label"
            class="advisor-section__metric"
          >
            <span class="advisor-section__metric-label">{{ m.label }}</span>
            <span
              class="advisor-section__metric-value"
              :class="riseFallClass(m.value)"
            >
              {{ fmtPct(m.value) }}
            </span>
          </li>
        </ul>
      </div>

      <div v-if="riskMetrics.length" class="advisor-section__metrics">
        <h4 class="advisor-section__metrics-title">风险指标</h4>
        <ul class="advisor-section__metrics-list">
          <li
            v-for="m in riskMetrics"
            :key="m.label"
            class="advisor-section__metric"
          >
            <span class="advisor-section__metric-label">{{ m.label }}</span>
            <span class="advisor-section__metric-value">{{ m.text }}</span>
          </li>
        </ul>
      </div>

      <p v-if="strategyText" class="advisor-section__desc">
        {{ strategyText }}
      </p>

      <!-- 成分基金：复用已上线的 holdings 端点；已收录本地名录的才给跳转 -->
      <div
        v-if="holdings && holdings.holdings.length"
        class="advisor-section__block"
      >
        <h4 class="advisor-section__metrics-title">
          成分基金（{{ holdings.holdings.length }}）
          <span v-if="holdings.as_of_date" class="advisor-section__sub">
            快照 {{ holdings.as_of_date }}
          </span>
        </h4>
        <ul class="advisor-section__holdings">
          <li
            v-for="h in holdings.holdings"
            :key="h.fund_code"
            class="advisor-section__holding"
          >
            <RouterLink
              v-if="h.in_local_db"
              :to="productRoute({ assetType: 'fund', symbol: h.fund_code })"
              class="advisor-section__holding-name advisor-section__holding-name--link"
            >
              {{ h.fund_name || h.fund_code }}
            </RouterLink>
            <span v-else class="advisor-section__holding-name">
              {{ h.fund_name || h.fund_code }}
            </span>
            <span class="advisor-section__holding-ratio">
              {{
                h.after_ratio != null ? `${h.after_ratio.toFixed(2)}%` : DASH
              }}
            </span>
          </li>
        </ul>
      </div>

      <!-- 脚注：来源给平台名（用户看得懂），并附官方页面外链（新窗口打开） -->
      <p class="advisor-section__footnote">
        数据来源：{{ platformLabel || profile.platform }}
        <template v-if="profile.source_url">
          ·
          <a
            :href="profile.source_url"
            target="_blank"
            rel="noopener noreferrer"
            referrerpolicy="no-referrer"
            class="advisor-section__link"
          >
            查看官方组合页面
          </a>
        </template>
      </p>
      <p class="advisor-section__footnote">
        组合构成与收益以平台官方披露为准；平台未披露的字段显示「—」
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.advisor-section__facts {
  display: grid;

  /* auto-fit + 真实最小列宽：`minmax(0, 1fr)` 会让轨道塌到几像素、标签逐字竖排（#1969 P0） */
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.advisor-section__fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.advisor-section__label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.advisor-section__value {
  margin: 0;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.advisor-section__value--strong {
  font-size: 18px;
  font-weight: 600;
}

.advisor-section__value--wrap {
  overflow-wrap: anywhere;
}

.advisor-section__sub {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.advisor-section__metrics {
  margin-top: var(--space-3);
}

.advisor-section__metrics-title {
  margin: 0 0 var(--space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.advisor-section__metrics-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-3);
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-section__metric {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.advisor-section__metric-label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.advisor-section__metric-value {
  font-size: 16px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 文字级涨跌色（仓库专为文字维护的 AA 对比度色，勿用图形级 --color-rise/fall） */
.advisor-section__metric-value.is-rise {
  color: var(--color-rise-ink);
}

.advisor-section__metric-value.is-fall {
  color: var(--color-fall-ink);
}

.advisor-section__desc {
  margin: var(--space-3) 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.advisor-section__block {
  margin-top: var(--space-3);
}

.advisor-section__holdings {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-2) var(--space-6);
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-section__holding {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  min-width: 0;
}

.advisor-section__holding-name {
  font-size: 13px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.advisor-section__holding-name--link {
  text-decoration: none;
}

.advisor-section__holding-name--link:hover {
  text-decoration: underline;
}

.advisor-section__holding-ratio {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.advisor-section__hint,
.advisor-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.advisor-section__footnote:first-of-type {
  margin-top: var(--space-3);
}

.advisor-section__link {
  color: var(--text-secondary);
}
</style>
