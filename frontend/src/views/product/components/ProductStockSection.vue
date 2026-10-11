<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { assetTypeLabel, useEnumLabels } from "@/composables/useEnumLabels";
import { getStockProfile, type StockProfileResult } from "@/api/products";

/**
 * 详情页「场内行情」区块（#1969 股票 · #1974 起 ETF · 设计 §5 / §6 品类矩阵）。
 *
 * 命名仍是 `ProductStockSection`，但职责自 #1974 起扩为**场内证券口径**
 * （`stock` / `etf`）：两者同落`securities` 表、同走 `stock-profile` 端点、
 * 同用 `price_history` 日线，故复用本区块而非复制一份（设计 §6「ETF 与基金区块
 * 高度同构，可复用」在**取数层同样成立**）。
 *
 * **注意不能用 `fund-profile` 取 ETF 资料**（设计 §6 那句只对 UI 展示层成立）：
 * `services/fund_profile.py` 只查 `funds` 表的 6 位场外裸码，ETF 是场内码
 * （如 `510300`），挂上去直接 404。
 *
 * 取数一次到位：`GET /api/products/stock-profile/` 一次返回基本资料 + 区间行情。
 * 为什么这些字段必须后端直出（而非前端拼）：
 *
 * - 现有唯一的高低价值出口 `securities/<symbol>/price-range/` 是**指定单日**语义
 *   （#948 记账回填用），要拿「近 60 日高低」得发 60 次请求，或把整段明细拉进浏览器
 *   自己 min/max——前者拖慢首屏，后者违反「明细不在前端算」的数据策略；
 * - 行业 / 币种等资料项在 securities 域也没有出口。
 *
 * 口径与降级：
 * - **走势曲线不在这里画**——它由同页的 `ProductTrendSection`（#1967）负责，本区块
 *   只做「资料 + 区间统计」，避免同一页出现两条行情取数链路（issue 验收项）；
 * - `change_pct` 为 null 意为「窗口首日缺失或为 0」，**不是「没涨」**，故显示「—」；
 * - 一条行情行都没有时不报错：行情区转为空态文案，资料项照常展示；
 * - 行情条数不足窗口时（次新股 / 上市不满 60 个交易日）如实提示实际条数，
 *   不假装统计了整个窗口；
 * - 资料缺项逐项降级为「—」，**不用 mock 顶替**（设计 §10）；
 * - ETF 不展示「行业」：它是指数化产品，`securities.sector` 对 ETF 基本恒空，
 *   摆一行恒为「—」的字段只是噪声（不是缺数据，是这一维度对它不适用）。
 */

const props = defineProps<{
  symbol: string;
  /** 市场消歧：同码跨市场时由 resolve 结果带下来 */
  market?: string;
  /**
   * 品类（#1974）：只影响标题 / 空态文案与「行业」项是否展示，取数端点两者相同。
   * 缺省按 `stock` 处理，保持 #1969 的原行为（调用方不传也不会变形）。
   */
  assetType?: string;
}>();

/** 是否 ETF：文案与字段取舍的唯一分歧点，其余逻辑与股票完全一致 */
const isEtf = computed(
  () => (props.assetType || "stock").trim().toLowerCase() === "etf"
);
const sectionTitle = computed(() => (isEtf.value ? "ETF 行情" : "股票行情"));
const loadingHint = computed(() =>
  isEtf.value ? "正在读取 ETF 行情…" : "正在读取股票行情…"
);
const emptyHint = computed(() =>
  isEtf.value ? "暂无可展示的 ETF 行情" : "暂无可展示的股票行情"
);

const { ensure: ensureEnums, marketLabel } = useEnumLabels();

onMounted(() => {
  // 市场码 → 中文：真相源在后端 /enums，前端无镜像，必须等拉取完成（同 detail.vue）
  void ensureEnums();
});

const loading = ref(false);
const profile = ref<StockProfileResult | null>(null);
const failed = ref(false);

const DASH = "—";

/** 有没有可展示的行情：一条行情行都没有时，区间高/低/涨跌都无意义 */
const hasQuote = computed(
  () => !!profile.value && profile.value.trading_days > 0
);

/** 历史不足一个完整窗口：按实际条数如实说明，而不是一律写「近 60 日」 */
const shortHistory = computed(() => {
  const p = profile.value;
  return !!p && p.trading_days > 0 && p.trading_days < p.window_days;
});

function formatPrice(value: number | null) {
  return value != null ? value.toFixed(2) : DASH;
}

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getStockProfile({
      symbol: props.symbol,
      market: props.market
    });
    profile.value = res.data;
  } catch {
    // 未收录 / 网络异常：降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => [props.symbol, props.market], load, { immediate: true });
</script>

<template>
  <CardBlock class="stock-section">
    <SectionHeader :title="sectionTitle" />

    <p v-if="loading" class="stock-section__hint">{{ loadingHint }}</p>

    <p v-else-if="failed || !profile" class="stock-section__hint">
      {{ emptyHint }}
    </p>

    <template v-else>
      <!-- 区间行情：无行情行时整段转空态，资料项照常展示 -->
      <template v-if="hasQuote">
        <dl class="stock-section__quote">
          <div class="stock-section__quote-item">
            <dt class="stock-section__label">最新收盘</dt>
            <dd class="stock-section__value stock-section__value--strong">
              {{ formatPrice(profile.close) }}
            </dd>
          </div>
          <div class="stock-section__quote-item">
            <dt class="stock-section__label">区间涨跌</dt>
            <dd class="stock-section__value">
              <RiseFallText
                v-if="profile.change_pct != null"
                :value="profile.change_pct"
                size="sm"
              />
              <span v-else>{{ DASH }}</span>
            </dd>
          </div>
          <div class="stock-section__quote-item">
            <dt class="stock-section__label">行情日期</dt>
            <dd class="stock-section__value">
              {{ profile.quote_date || DASH }}
            </dd>
          </div>
        </dl>

        <dl class="stock-section__facts">
          <div class="stock-section__fact">
            <dt class="stock-section__label">区间最高</dt>
            <dd class="stock-section__value">
              {{ formatPrice(profile.high) }}
            </dd>
          </div>
          <div class="stock-section__fact">
            <dt class="stock-section__label">区间最低</dt>
            <dd class="stock-section__value">{{ formatPrice(profile.low) }}</dd>
          </div>
          <div class="stock-section__fact">
            <dt class="stock-section__label">区间窗口</dt>
            <dd class="stock-section__value">
              近 {{ profile.trading_days }} 个交易日
            </dd>
          </div>
        </dl>
      </template>

      <p v-else class="stock-section__hint">暂无行情数据，区间统计不可用</p>

      <!-- 基本资料：与行情独立，行情缺失也该看得到 -->
      <dl class="stock-section__facts">
        <div class="stock-section__fact">
          <dt class="stock-section__label">品类</dt>
          <dd class="stock-section__value">
            {{ assetTypeLabel(profile.asset_type) || DASH }}
          </dd>
        </div>
        <div class="stock-section__fact">
          <dt class="stock-section__label">市场</dt>
          <dd class="stock-section__value">
            {{ marketLabel(profile.market) || DASH }}
          </dd>
        </div>
        <div class="stock-section__fact">
          <dt class="stock-section__label">币种</dt>
          <dd class="stock-section__value">{{ profile.currency || DASH }}</dd>
        </div>
        <div v-if="!isEtf" class="stock-section__fact">
          <dt class="stock-section__label">行业</dt>
          <dd class="stock-section__value">{{ profile.sector || DASH }}</dd>
        </div>
      </dl>

      <!-- 来源给站点名（用户看得懂），不再写 price_history 这类表名（#1969） -->
      <p v-if="profile.source" class="stock-section__footnote">
        数据来源：{{ profile.source }}（{{ profile.basis }}）
      </p>
      <p v-if="shortHistory" class="stock-section__footnote">
        历史仅 {{ profile.trading_days }} 个交易日（不足
        {{ profile.window_days }} 日窗口），按实际可用数据统计
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.stock-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.stock-section__quote {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.stock-section__quote-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.stock-section__label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.stock-section__value {
  margin: 0;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.stock-section__value--strong {
  font-size: 18px;
  font-weight: 600;
}

.stock-section__facts {
  display: grid;

  /* auto-fit + 真实最小列宽（#1969 P0 截图修复）：
     · `minmax(0, 1fr)` 让轨道可收缩到 0 → 列宽塌成几像素，标签逐字竖排、数值被截断；
     · `auto-fill` 不折叠空轨道，项少时右侧留大片空白；`auto-fit` 才会把剩余列拉伸填满。 */
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.stock-section__fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.stock-section__hint,
.stock-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
