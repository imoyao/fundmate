<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  getAdvisorComparison,
  type AdvisorComparisonFund,
  type AdvisorComparisonResult
} from "@/api/funds";
import { productRoute } from "@/utils/productIdentity";
import { DASH } from "./advisorModel";

/**
 * 跨组合对比（调仓解读付费功能 · L3）—— 我的「账户集」 vs 本投顾组合。
 *
 * ## 回答什么问题
 *
 * 「它重仓的基金，我持没持、差多少」——基金代码级三集合：
 * - **共同持有**：投顾占比 + 我持仓市值，两列并列；
 * - **投顾独有**：它持有、我没有（可能是我该关注的方向）；
 * - **我独有**：我持有、它没有（只列我的持仓，不做「该不该卖」的暗示）。
 *
 * ## 口径（与后端 advisor_comparison 一致，勿改）
 *
 * - 基金代码级重合（不做穿透到股票——投顾组合不披露股票级持仓，穿透只能近似）；
 * - 货基 / 债基已剔除（投顾侧按 fund_types 名、我侧按 positions.type）；
 * - 「混合型」未细分偏股/偏债，暂归权益类（已知口径妥协）。
 *
 * ## 诚实降级（设计 §6）
 *
 * - 组合不存在 / 接口异常 → 整块不渲染（父区块的档案仍照常展示）；
 * - 任一侧 `degraded=true` → 显示「暂时取不到」，**不拿 0 冒充**；
 * - 我的账户集侧**没有**回撤 / 夏普指标（后端 mine 侧只回持仓与总市值），
 *   故指标对照只列投顾侧，我的侧指标是后续 L2 补全的事——不编造占位值。
 *
 * ## 合规边界（design §2）
 *
 * 只陈述客观数据（「它重仓 X 占 16%，你持有 X」），**不写「它更强、建议替换」**。
 */
const props = defineProps<{
  /** 平台组合码（advisor_portfolios.code） */
  code: string;
}>();

const loading = ref(false);
const failed = ref(false);
const result = ref<AdvisorComparisonResult | null>(null);

async function load() {
  if (!props.code) return;
  loading.value = true;
  failed.value = false;
  result.value = null;
  try {
    const res = await getAdvisorComparison(props.code);
    result.value = res.data;
  } catch {
    // 组合不存在 / 未收录 / 网络异常：整块降级为空态，不影响父区块其余子件
    result.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.code, load, { immediate: true });

/** 三集合各自是否可展示（有数据才渲染对应段） */
const common = computed(() => result.value?.overlap.common ?? []);
const advisorOnly = computed(() => result.value?.overlap.advisor_only ?? []);
const mineOnly = computed(() => result.value?.overlap.mine_only ?? []);

/** 投顾侧指标（我的侧暂无指标，只列投顾） */
const advisorMetrics = computed(() => {
  const a = result.value?.advisor;
  if (!a) return [];
  const items: { label: string; text: string | null }[] = [
    {
      label: "最大回撤",
      text: a.max_drawdown != null ? `${a.max_drawdown.toFixed(2)}%` : null
    },
    {
      label: "夏普比率",
      text: a.sharpe_ratio != null ? a.sharpe_ratio.toFixed(3) : null
    },
    {
      label: "年化波动率",
      text: a.volatility != null ? `${a.volatility.toFixed(2)}%` : null
    }
  ];
  return items.filter(i => i.text != null);
});

function nameOf(item: AdvisorComparisonFund): string {
  return item.fund_name || item.fund_code;
}

function ratioText(item: AdvisorComparisonFund): string {
  return item.advisor_ratio != null ? `${item.advisor_ratio.toFixed(2)}%` : DASH;
}

function marketValueText(cents: number | null): string {
  if (cents == null) return DASH;
  // 分 → 元，千分位；市值不足 1 万保留两位，超过省略到万。与 sankeyLayout 同款
  const yuan = cents / 100;
  if (yuan >= 10000) {
    return `¥${(yuan / 10000).toFixed(1)}万`;
  }
  return `¥${yuan.toLocaleString()}`;
}
</script>

<template>
  <div
    v-if="!loading && !failed && result"
    class="advisor-section__block advisor-comparison"
  >
    <h4 class="advisor-section__metrics-title">
      与我的持仓对比
      <span
        v-if="result.advisor.as_of_date"
        class="advisor-section__sub"
      >
        快照 {{ result.advisor.as_of_date }}
      </span>
    </h4>

    <!-- 投顾侧指标（我的账户集侧暂无指标，只列投顾，不编造） -->
    <ul
      v-if="advisorMetrics.length"
      class="advisor-section__metrics-list advisor-comparison__metrics"
    >
      <li
        v-for="m in advisorMetrics"
        :key="m.label"
        class="advisor-section__metric"
      >
        <span class="advisor-section__metric-label">{{ m.label }}</span>
        <span class="advisor-section__metric-value">{{ m.text }}</span>
      </li>
    </ul>

    <!-- 三集合：共同持有 / 投顾独有 / 我独有 -->
    <div
      v-if="common.length"
      class="advisor-comparison__set"
    >
      <p class="advisor-comparison__set-title">共同持有（{{ common.length }}）</p>
      <ul class="advisor-comparison__rows">
        <li
          v-for="item in common"
          :key="item.fund_code"
          class="advisor-comparison__row"
        >
          <span class="advisor-comparison__name">
            <RouterLink
              :to="productRoute({ assetType: 'fund', symbol: item.fund_code })"
              class="advisor-comparison__link"
              :title="nameOf(item)"
            >
              {{ nameOf(item) }}
            </RouterLink>
          </span>
          <span class="advisor-comparison__ratio">{{ ratioText(item) }}</span>
          <span class="advisor-comparison__value">
            {{ marketValueText(item.my_market_value_cents) }}
          </span>
        </li>
      </ul>
    </div>

    <div
      v-if="advisorOnly.length"
      class="advisor-comparison__set"
    >
      <p class="advisor-comparison__set-title">
        投顾持有 · 我没有（{{ advisorOnly.length }}）
      </p>
      <ul class="advisor-comparison__rows">
        <li
          v-for="item in advisorOnly"
          :key="item.fund_code"
          class="advisor-comparison__row"
        >
          <span class="advisor-comparison__name">
            <RouterLink
              :to="productRoute({ assetType: 'fund', symbol: item.fund_code })"
              class="advisor-comparison__link"
              :title="nameOf(item)"
            >
              {{ nameOf(item) }}
            </RouterLink>
          </span>
          <span class="advisor-comparison__ratio">{{ ratioText(item) }}</span>
          <span class="advisor-comparison__value advisor-comparison__value--muted">
            —
          </span>
        </li>
      </ul>
    </div>

    <div
      v-if="mineOnly.length"
      class="advisor-comparison__set"
    >
      <p class="advisor-comparison__set-title">
        我持有 · 投顾没有（{{ mineOnly.length }}）
      </p>
      <ul class="advisor-comparison__rows">
        <li
          v-for="item in mineOnly"
          :key="item.fund_code"
          class="advisor-comparison__row"
        >
          <span class="advisor-comparison__name">
            <RouterLink
              :to="productRoute({ assetType: 'fund', symbol: item.fund_code })"
              class="advisor-comparison__link"
              :title="nameOf(item)"
            >
              {{ nameOf(item) }}
            </RouterLink>
          </span>
          <span class="advisor-comparison__ratio advisor-comparison__ratio--muted">
            —
          </span>
          <span class="advisor-comparison__value">
            {{ marketValueText(item.my_market_value_cents) }}
          </span>
        </li>
      </ul>
    </div>

    <!-- 降级：任一侧取数失败，不拿 0 冒充 -->
    <p
      v-if="result.advisor.degraded || result.mine.degraded"
      class="advisor-comparison__degraded"
    >
      部分持仓暂时取不到，对比结果可能不完整
    </p>

    <!-- 口径声明（含非投资建议） -->
    <p class="advisor-comparison__caveats">
      {{ result.caveats.join(" ") }}
    </p>
  </div>
</template>

<style lang="scss" scoped>
@use "./advisor-base";

.advisor-comparison__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--space-3);
  padding: 0;
  margin: 0 0 var(--space-2);
  list-style: none;
}

.advisor-comparison__set {
  margin-top: var(--space-2);
}

.advisor-comparison__set-title {
  margin: 0 0 var(--space-1);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-comparison__rows {
  display: grid;
  gap: 0;
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-comparison__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px 72px;
  gap: var(--space-2);
  place-items: center end;
  height: var(--space-loose);
  padding: 0 var(--space-1);
  border-radius: var(--radius-xs);

  &:hover {
    background: var(--bg-soft);
  }
}

.advisor-comparison__name {
  justify-self: stretch;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.advisor-comparison__link {
  font-size: var(--text-label);
  color: var(--text-primary);
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.advisor-comparison__ratio,
.advisor-comparison__value {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  white-space: nowrap;
}

.advisor-comparison__ratio--muted,
.advisor-comparison__value--muted {
  color: var(--text-tertiary-ink);
}

.advisor-comparison__degraded {
  margin-top: var(--space-2);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-comparison__caveats {
  margin-top: var(--space-2);
  font-size: calc(var(--text-label) - 1px);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
