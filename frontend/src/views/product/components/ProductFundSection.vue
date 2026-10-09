<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getFundProfile, type FundProfileResult } from "@/api/products";

/**
 * 详情页「基金资料」区块（#1968 · 设计 §5 C 区块）。
 *
 * 取数一次到位：`GET /api/products/fund-profile/` 把净值、日涨跌、费率、经理、类型、
 * 规模打包返回——这些原先要么没有端点（经理）、要么要串行两三次（净值 + 前一日净值）。
 *
 * 口径与降级：
 * - **「我的成本 / 持有收益」不在这里重复渲染**——它属于持仓区块（#1966 的
 *   `ProductPositionSection`），同一份持仓取一次即可，两处各拉一遍是自找的 N+1；
 * - `change_pct` 为 null 意为「**前一日净值缺失**」，不是「今天没涨」，故显示「—」；
 * - 类型 / 经理 / 规模等参考信息缺失逐项降级为「—」，**不用 mock 顶替**（G1 教训）。
 */

const props = defineProps<{
  symbol: string;
}>();

const loading = ref(false);
const profile = ref<FundProfileResult | null>(null);
const failed = ref(false);

const DASH = "—";

/** 申购费率：阶梯取首档（金额下限最小的档），并标注是否分档 */
const purchaseRate = computed(() => {
  const rows = profile.value?.fee_rates?.purchase ?? [];
  if (!rows.length) return null;
  const first = rows[0];
  return {
    text: `${(first.rate * 100).toFixed(2)}%`,
    tiered: rows.length > 1
  };
});

/** 赎回费：持有 ≤ 某天数时的费率（首档），分档时标注 */
const redeemRate = computed(() => {
  const rows = profile.value?.fee_rates?.redeem ?? [];
  if (!rows.length) return null;
  const first = rows[0];
  return {
    text: `${(first.rate * 100).toFixed(2)}%`,
    days: first.start_day,
    tiered: rows.length > 1
  };
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getFundProfile(props.symbol);
    profile.value = res.data;
  } catch {
    // 非基金代码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="fund-section">
    <SectionHeader title="基金资料" />

    <p v-if="loading" class="fund-section__hint">正在读取基金资料…</p>

    <p v-else-if="failed || !profile" class="fund-section__hint">
      暂无可展示的基金资料
    </p>

    <template v-else>
      <!-- 首屏：单位净值 + 日涨跌 + 净值日期 -->
      <dl class="fund-section__nav">
        <div class="fund-section__nav-item">
          <dt class="fund-section__label">单位净值</dt>
          <dd class="fund-section__value">
            {{ profile.unit_nav != null ? profile.unit_nav.toFixed(4) : DASH }}
          </dd>
        </div>
        <div class="fund-section__nav-item">
          <dt class="fund-section__label">日涨跌</dt>
          <dd class="fund-section__value">
            <RiseFallText
              v-if="profile.change_pct != null"
              :value="profile.change_pct"
              size="sm"
            />
            <span v-else>{{ DASH }}</span>
          </dd>
        </div>
        <div class="fund-section__nav-item">
          <dt class="fund-section__label">净值日期</dt>
          <dd class="fund-section__value">{{ profile.nav_date || DASH }}</dd>
        </div>
      </dl>

      <dl class="fund-section__facts">
        <div class="fund-section__fact">
          <dt class="fund-section__label">基金类型</dt>
          <dd class="fund-section__value">{{ profile.fund_type || DASH }}</dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">基金公司</dt>
          <dd class="fund-section__value">{{ profile.company || DASH }}</dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">基金经理</dt>
          <dd class="fund-section__value">
            {{
              profile.managers.length
                ? profile.managers.map(m => m.name).join("、")
                : DASH
            }}
          </dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">规模</dt>
          <dd class="fund-section__value">
            <template v-if="profile.scale != null">
              {{ profile.scale.toFixed(2) }} 亿元
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">成立日期</dt>
          <dd class="fund-section__value">{{ profile.create_time || DASH }}</dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">申购费率</dt>
          <dd class="fund-section__value">
            <template v-if="purchaseRate">
              {{ purchaseRate.text
              }}<span v-if="purchaseRate.tiered" class="fund-section__tier"
                >起</span
              >
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">赎回费率</dt>
          <dd class="fund-section__value">
            <template v-if="redeemRate">
              {{ redeemRate.text
              }}<span class="fund-section__tier"
                >（{{ redeemRate.days }} 天内）</span
              >
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="fund-section__fact">
          <dt class="fund-section__label">业绩基准</dt>
          <dd class="fund-section__value fund-section__value--wrap">
            {{ profile.benchmark || DASH }}
          </dd>
        </div>
      </dl>

      <p class="fund-section__footnote">
        净值来源：daily_worth 单位净值 · 费率来源：funds 费率阶梯
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.fund-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.fund-section__nav {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.fund-section__nav-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.fund-section__label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.fund-section__value {
  margin: 0;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.fund-section__value--wrap {
  word-break: break-all;
}

.fund-section__facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(0, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.fund-section__fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.fund-section__tier {
  margin-left: var(--space-1);
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.fund-section__hint,
.fund-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
