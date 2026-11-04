<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getFundProfile, type FundProfileResult } from "@/api/products";
import FundFeeGuide from "./FundFeeGuide.vue";
import {
  purchaseFeeText,
  redeemFeeLadder,
  redeemFeeText
} from "./fundFeeFormat";
import { formatRatingDeltaText, formatRatingText } from "./fundRatingFormat";

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

/** 费率文案与阶梯（#1015）：口径（小数费率、半开区间、取最小档）全在纯函数里，
 *  组件只管取数与渲染——旧实现把 `rows[0]` 当首档、把 `start_day` 当条件，
 *  接口换个顺序就会把「持有 2 年以上 0%」显示成赎回费率。 */
const purchaseFee = computed(() =>
  purchaseFeeText(profile.value?.fee_rates?.purchase)
);

const redeemFee = computed(() =>
  redeemFeeText(profile.value?.fee_rates?.redeem)
);

/** 赎回费阶梯明细：折叠区里解释「格子里为什么只有一个数」 */
const redeemTiers = computed(() =>
  redeemFeeLadder(profile.value?.fee_rates?.redeem)
);

/** 基金经理列表：接口缺字段时为 null（FundProfileResult 契约：缺失一律降级），
 *  统一收敛为空数组——模板不裸取 .length（#2191：缺字段时渲染抛错，Vue 中止
 *  更新，整个区块永远停在「正在读取」）。 */
const managerList = computed(() => profile.value?.managers ?? []);

/** 晨星评级文案（#1440）：口径与守卫都在纯函数里（`fundRatingFormat.ts`），
 *  组件只做取数——模板里内联的 `v-if` 没人能钉住「缺失 ≠ 0 星」这类口径。 */
const ratingText = computed(() =>
  formatRatingText(profile.value?.morningstar_rating)
);

/** 评级较上期的变化：只表达方向与幅度（上期值不展示——当期值列不存历史）。 */
const ratingDeltaText = computed(() =>
  formatRatingDeltaText(profile.value?.morningstar_rating_delta)
);

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

    <p v-if="loading" class="section-footnote">正在读取基金资料…</p>

    <p v-else-if="failed || !profile" class="section-footnote">
      暂无可展示的基金资料
    </p>

    <template v-else>
      <!-- 首屏：单位净值 + 日涨跌 + 净值日期 -->
      <dl class="fund-section__nav">
        <div class="fund-section__nav-item">
          <dt class="facts-grid__label">单位净值</dt>
          <dd class="facts-grid__value">
            {{ profile.unit_nav != null ? profile.unit_nav.toFixed(4) : DASH }}
          </dd>
        </div>
        <div class="fund-section__nav-item">
          <dt class="facts-grid__label">日涨跌</dt>
          <dd class="facts-grid__value">
            <RiseFallText
              v-if="profile.change_pct != null"
              :value="profile.change_pct"
              size="sm"
            />
            <span v-else>{{ DASH }}</span>
          </dd>
        </div>
        <div class="fund-section__nav-item">
          <dt class="facts-grid__label">净值日期</dt>
          <dd class="facts-grid__value">{{ profile.nav_date || DASH }}</dd>
        </div>
      </dl>

      <dl class="facts-grid">
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">基金类型</dt>
          <dd class="facts-grid__value">{{ profile.fund_type || DASH }}</dd>
        </div>
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">基金公司</dt>
          <dd class="facts-grid__value">{{ profile.company || DASH }}</dd>
        </div>
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">基金经理</dt>
          <dd class="facts-grid__value facts-grid__value--wrap">
            <template v-if="managerList.length">
              <template v-for="(m, i) in managerList" :key="m.mgr_code">
                <span v-if="i > 0" aria-hidden="true">、</span>{{ m.name
                }}<span v-if="m.is_classic" class="fund-section__badge"
                  >代表作</span
                >
              </template>
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">规模</dt>
          <dd class="facts-grid__value">
            <template v-if="profile.scale != null">
              {{ profile.scale.toFixed(2) }} 亿元
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">成立日期</dt>
          <dd class="facts-grid__value">{{ profile.create_time || DASH }}</dd>
        </div>
        <!-- 晨星 3 年期星级（#1440）：源为东财评级总汇页，与净值/费率链路不同源，
             故在格内自带机构与期限口径，不并入页脚「数据来源」标签。 -->
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">晨星评级</dt>
          <dd class="facts-grid__value facts-grid__value--wrap">
            <template v-if="ratingText">
              {{ ratingText
              }}<span v-if="ratingDeltaText" class="fund-section__tier"
                >（{{ ratingDeltaText }}）</span
              >
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <!-- 费率两格只在格内给「最低一档 + 适用条件」，口径说明与阶梯明细收在下方
             折叠区（#1015）：14px 的格子里塞不下「按金额分档、赎回费首档是惩罚档」
             这类话，硬塞会让两行数字变成一片小字。 -->
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">申购费率</dt>
          <dd class="facts-grid__value facts-grid__value--wrap">
            <template v-if="purchaseFee">
              {{ purchaseFee.rate
              }}<span class="fund-section__tier"
                >（{{ purchaseFee.condition
                }}<template v-if="purchaseFee.tiered">，分档递减</template
                >）</span
              >
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="facts-grid__cell">
          <dt class="facts-grid__label">赎回费率</dt>
          <dd class="facts-grid__value facts-grid__value--wrap">
            <template v-if="redeemFee">
              {{ redeemFee.rate
              }}<span class="fund-section__tier"
                >（{{ redeemFee.condition
                }}<template v-if="redeemFee.tiered">，分档递减</template
                >）</span
              >
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="fund-section__fact facts-grid__cell--wide">
          <dt class="facts-grid__label">业绩基准</dt>
          <dd class="facts-grid__value facts-grid__value--wrap">
            {{ profile.benchmark || DASH }}
          </dd>
        </div>
      </dl>

      <!-- 费率科普（#1015）：唯一没有后端字段归属的维度——费率数字属 data，
           「怎么读」属知识，故落在前端静态文案里（子组件，主区块不再长行数）。 -->
      <FundFeeGuide :tiers="redeemTiers" />

      <!-- 来源给站点名：净值 / 费率 / 基础资料整条链路都走天天基金（#1969） -->
      <p class="section-footnote">数据来源：{{ profile.source }}</p>
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

/* 整句型字段跨列占满整行（业绩基准）。网格是 `minmax(140px, 1fr)`，
   业绩基准那类「沪深300指数收益率*85% + 中证500指数收益率*15%」的整句描述
   挤在 140px 里只能疯狂换行——不是「必要的折行」，是被窄格逼出来的逐字断行。
   它本来就是一个段落，不是指标卡，让它独占一行。 */

.fund-section__tier {
  margin-left: var(--space-1);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 代表作品徽标（#1968）：标记该经理在此基金上是代表作品，数据来自 fund_managers.is_classic。
   #2314：对齐 design.md Badge 规范（pill + 11px），文字改 info 文字级令牌（原 --color-info
   作文字仅 2.90:1，#1599 batch 3 已立 -ink）。 */
.fund-section__badge {
  padding: 0 var(--space-2);
  margin-left: var(--space-1);
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--color-info-ink);
  background: color-mix(in srgb, var(--color-info) 12%, transparent);
  border-radius: var(--radius-pill);
}

/* 费率科普折叠（#1015）的样式在 `FundFeeGuide.vue` 里——它是独立的可点区块，
   与本次指标格无关，留在本文件会把「资料网格」和「科普」两套规则混在一起。 */
</style>
