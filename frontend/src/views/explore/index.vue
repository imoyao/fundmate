<!-- frontend/src/views/explore/index.vue -->
<template>
  <div class="explore-page">
    <!-- ===== 顶部导航（公共组件，与温度计完全一致） ===== -->
    <MarketHeader :logo="MARKET_LOGO" badge="探市" :navs="headerNavs" />

    <!-- ============================================================ -->
    <!-- 温度数据仪表盘                                                -->
    <!-- ============================================================ -->
    <!-- 温度数据仪表盘（#984 拆分至 components/ExploreTemperatureDashboard.vue） -->
    <ExploreTemperatureDashboard
      ref="dashboardRef"
      @go-temperature="goToTemperature"
    />

    <!-- ============================================================ -->
    <!-- 添加/观察栏（仅未登录；登录后隐藏，引导去自选页管理）       -->
    <!-- ============================================================ -->
    <!-- 添加/观察栏（#984 拆分至 components/ExploreAddSection.vue；仅未登录渲染） -->
    <ExploreAddSection
      v-if="!isAuthenticated"
      id="add-section"
      :add-holding="addHolding"
      :quotes-map="quotesMap"
    />

    <!-- 已登录：引导去自选页（探市只做展示与观察，管理能力收敛到登录后的自选） -->
    <section v-if="isAuthenticated" class="auth-guide">
      <div class="auth-guide__inner">
        <div class="auth-guide__text">
          <div class="auth-guide__title">已登录，可前往自选页管理资产</div>
          <div class="auth-guide__desc">
            探市页仅用于浏览市场数据；分组、标签、AI
            批量导入等功能已迁移至自选页统一管理。
          </div>
        </div>
        <el-button type="primary" @click="goToWatchlist">
          前往自选页
          <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
        </el-button>
      </div>
    </section>

    <!-- ============================================================ -->
    <!-- 观察列表                                                     -->
    <!-- ============================================================ -->
    <section class="watchlist-section">
      <div class="summary-bar">
        <div class="summary-left">
          <span class="summary-count">共 {{ totalCount }} 项</span>
          <template v-if="!isPureObservationMode && summary">
            <span class="summary-divider">|</span>
            <span class="summary-value"
              >总市值
              <MoneyDisplay
                :value="summary.totalMarketValue"
                :show-sign="false"
            /></span>
            <span class="summary-divider">|</span>
            <span class="summary-pnl"
              >盈亏 <RiseFallText :value="summary.totalPnl" suffix=""
            /></span>
          </template>
          <span v-if="isPureObservationMode" class="summary-hint"
            >输入成本与份额后可查看持仓盈亏</span
          >
        </div>
        <div class="summary-right">
          <span class="status-indicator">
            <span class="status-dot" :class="statusClass" />{{ statusText }}
          </span>
          <el-select
            :model-value="refreshInterval"
            size="small"
            class="refresh-interval-select"
            @change="setRefreshInterval"
          >
            <el-option
              v-for="s in REFRESH_INTERVAL_OPTIONS"
              :key="s"
              :label="`${s}s 刷新`"
              :value="s"
            />
          </el-select>
          <span v-if="lastUpdateTime" class="update-time"
            >更新: {{ formatDateTime(lastUpdateTime) }}</span
          >
          <el-button size="small" @click="manualRefresh">刷新</el-button>
        </div>
      </div>

      <!-- 表格视觉基线统一在 src/style/el-table.css 维护，勿在本页 :deep 覆盖 -->
      <el-table
        v-loading="loading"
        :data="tableData"
        border
        style="width: 100%"
        empty-text="暂无观察资产，添加你关注的标的开始研究"
      >
        <el-table-column label="产品" min-width="180">
          <template #default="{ row }">
            <ProductDisplay
              :name="row.name"
              :symbol="row.symbol"
              :type-label="getTypeLabel(row.type)"
            />
          </template>
        </el-table-column>

        <el-table-column label="最新价" width="120" align="right">
          <template #default="{ row }"
            ><MoneyDisplay
              :value="row.price"
              :show-sign="false"
              :precision="pricePrecision(row.type)"
          /></template>
        </el-table-column>

        <el-table-column label="涨跌幅" width="110" align="right">
          <template #default="{ row }"
            ><RiseFallText :value="row.changePct"
          /></template>
        </el-table-column>

        <el-table-column
          v-if="!isPureObservationMode"
          label="当日盈亏"
          width="130"
          align="right"
        >
          <template #default="{ row }"
            ><MoneyDisplay :value="row.pnl ?? 0" :show-sign="true"
          /></template>
        </el-table-column>

        <el-table-column
          v-if="!isPureObservationMode"
          label="持仓收益"
          width="130"
          align="right"
        >
          <template #default="{ row }"
            ><MoneyDisplay :value="row.positionPnl ?? 0" :show-sign="true"
          /></template>
        </el-table-column>

        <el-table-column label="深度分析" width="120" align="center">
          <template #default="{ row }">
            <el-dropdown @command="handleJump(row, $event)">
              <el-button size="small" type="primary" plain>分析 ▼</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="tool in getAvailableTools(row.type)"
                    :key="tool.key"
                    :command="tool.key"
                  >
                    {{ tool.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              link
              size="small"
              style="color: var(--text-tertiary)"
              @click="handleRemove(row.id)"
              >删除</el-button
            >
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============================================================ -->
    <!-- 底部（公共组件）：数据来源 + 免责声明                         -->
    <!-- ============================================================ -->
    <PageFooter
      revisit-text="探市页汇总指数快照与行业机会，辅助判断布局方向，不构成投资建议。"
      :revisit-items="[
        '回看探市各指数与行业的计算口径',
        '把当前行业冷热记录下来，做纵向对比',
        '关注公众号获取更多市场监测解读'
      ]"
      :sources="footerSources"
      copyright="© 2026 多多贝 · 让投资更从容"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { useLocalHoldings } from "@/composables/useLocalHoldings";
import {
  useRealtimeQuotes,
  REFRESH_INTERVAL_OPTIONS
} from "@/composables/useRealtimeQuotes";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import TemperatureLevelBadge from "@/components/TemperatureLevelBadge/index.vue";
import MarketHeader from "@/components/MarketHeader/index.vue";
import PageFooter from "@/components/PageFooter/index.vue";
import TemperatureGaugeCard from "@/components/TemperatureGaugeCard/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  MARKET_LOGO,
  useMarketHeaderNavs
} from "@/components/MarketHeader/config";
import { buildMarketFooterSources } from "@/components/MarketFooter/config";
import { batchFetchQuotes } from "@/utils/realtimeDataSources";
import { useTemperatureOverview } from "@/composables/temperature/useTemperatureOverview";
import ExploreTemperatureDashboard from "./components/ExploreTemperatureDashboard.vue";
import { getTypeLabel } from "@/constants/assetType";
import { pricePrecision } from "@/utils/pricePrecision";
import { useAuthState } from "@/composables/useAuthState";
import { formatDateTime } from "@/utils/date";

defineOptions({
  name: "ExplorePage"
});

// 登录态感知（探市免登录页）：登录后隐藏「添加观察」，引导去自选页管理（D4 + 方案 §3.3）
const { isAuthenticated } = useAuthState();

const router = useRouter();

// ================================================================
// 本地持仓
// ================================================================
let localHoldings;
try {
  localHoldings = useLocalHoldings();
} catch (e) {
  console.error("useLocalHoldings 初始化失败:", e);
  const fallbackHoldings = ref([]);
  localHoldings = {
    holdings: fallbackHoldings,
    addHolding: () => ({ success: false, message: "初始化失败" }),
    removeHolding: () => {},
    updateHolding: () => {},
    clearAll: () => {},
    getHoldingsForQuotes: () => [],
    isPureObservationMode: computed(() => false),
    totalCount: computed(() => 0)
  };
}

const holdings = localHoldings.holdings;
const addHolding = localHoldings.addHolding;
const removeHolding = localHoldings.removeHolding;
const getHoldingsForQuotes = localHoldings.getHoldingsForQuotes;
const totalCount = localHoldings.totalCount;
const isPureObservationMode = localHoldings.isPureObservationMode;

// ================================================================
// 实时估值
// ================================================================
const {
  items,
  summary,
  enabled,
  toggle,
  status,
  lastUpdateTime,
  refreshInterval,
  setRefreshInterval,
  manualRefresh
} = useRealtimeQuotes(
  () => {
    try {
      return getHoldingsForQuotes();
    } catch {
      return [];
    }
  },
  () => undefined
);

const quotesMap = computed(() => {
  const map: Record<string, any> = {};
  if (!items || !items.value) return map;
  items.value.forEach((item: any) => {
    if (item.symbol) {
      map[item.symbol] = item;
    }
  });
  return map;
});

watch(
  () => holdings.value,
  newHoldings => {
    if (enabled.value && newHoldings && newHoldings.length > 0) {
      manualRefresh();
    }
  },
  { deep: true }
);

// ================================================================
// 指数数据：已随温度仪表盘拆分至子组件（#984）
// ================================================================

// ================================================================
// 市场温度数据：已拆分至 components/ExploreTemperatureDashboard.vue（#984）。
// links（数据来源）经子组件 defineExpose 暴露，供 footer 使用。
// ================================================================
const dashboardRef = ref<{ links: Record<string, string> } | null>(null);

// ================================================================
// 表格数据
// ================================================================
const loading = ref(false);

const tableData = computed(() => {
  try {
    let hold: any[] = [];
    if (
      localHoldings &&
      typeof localHoldings.holdings === "object" &&
      "value" in localHoldings.holdings
    ) {
      const h = localHoldings.holdings.value;
      if (Array.isArray(h)) {
        hold = h;
      }
    }
    if (hold.length === 0) return [];

    const map = quotesMap.value;
    return hold.map(h => {
      const quote = map[h.symbol] || null;
      const price = quote?.currentPrice ?? 0;
      const changePct = quote?.changePct ?? 0;
      const cost = h.costPrice ?? 0;
      const qty = h.quantity ?? 0;
      const prevClose = quote?.prevClose ?? price;
      const pnl = (price - prevClose) * qty;
      const positionPnl = (price - cost) * qty;
      return {
        ...h,
        quote,
        price,
        changePct,
        pnl,
        positionPnl
      };
    });
  } catch {
    return [];
  }
});

// ================================================================
// 删除
// ================================================================
const handleRemove = (id: string) => {
  ElMessageBox.confirm("确定从观察列表中移除该资产吗？", "提示", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning"
  })
    .then(() => {
      removeHolding(id);
      ElMessage.success("已移除");
    })
    .catch(() => {});
};

// ================================================================
// 深度分析跳转
// ================================================================
const getAvailableTools = (type: string) => {
  const tools = [
    { key: "xueqiu", label: "雪球社区" },
    { key: "eastmoney", label: "东方财富" }
  ];
  if (type === "fund" || type === "etf") {
    tools.push({ key: "tiantian", label: "天天基金" });
  }
  return tools;
};

const handleJump = (row: any, command: string) => {
  let url = "";
  const code = row.symbol;
  const market = code.startsWith("6") ? "SH" : "SZ";
  const marketLower = code.startsWith("6") ? "sh" : "sz";

  switch (command) {
    case "xueqiu":
      url = `https://xueqiu.com/S/${market}${code}`;
      break;
    case "eastmoney":
      url = `https://quote.eastmoney.com/${marketLower}${code}.html`;
      break;
    case "tiantian":
      url = `https://fund.eastmoney.com/${code}.html`;
      break;
    default:
      return;
  }
  window.open(url, "_blank");
};

// ================================================================
// 状态指示器
// ================================================================
const statusClass = computed(() => {
  switch (status.value) {
    case "trading":
      return "status-trading";
    case "closed":
      return "status-closed";
    case "error":
      return "status-error";
    default:
      return "status-idle";
  }
});

const statusText = computed(() => {
  switch (status.value) {
    case "trading":
      return "实时更新";
    case "closed":
      return "休市中";
    case "error":
      return "连接异常";
    default:
      return "等待中";
  }
});

// ================================================================
// 页面方法
// ================================================================
const goToTemperature = () => {
  router.push("/temperature");
};

const goToWatchlist = () => {
  router.push("/watchlist");
};

// ================================================================
// Header / Footer 公共组件数据
// ================================================================
const headerNavs = useMarketHeaderNavs();

const footerSources = computed(() =>
  buildMarketFooterSources(dashboardRef.value?.links ?? {})
);

// ================================================================
// 生命周期
// ================================================================
onMounted(() => {
  if (!enabled.value) {
    toggle(true);
  }
});
</script>

<style lang="scss" scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

/* ============================================================
   8. 响应式
   ============================================================ */
@media (width <= 1024px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }

  .liquidity-card {
    flex-direction: row;
    gap: 20px;
    align-items: center;
  }

  .liquidity-divider {
    width: 1px;
    height: 64px;
  }
}

@media (width <= 768px) {
  .temperature-dashboard {
    padding: 0 16px 12px;
  }

  .snapshot-items {
    gap: 12px;
  }

  .liquidity-card {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .liquidity-metric {
    align-items: center;
    text-align: center;
  }

  .liquidity-divider {
    width: auto;
    height: 1px;
  }

  .liquidity-actions {
    flex-direction: row;
    justify-content: center;
  }
}

@media (width <= 480px) {
  .core-value {
    font-size: 26px;
  }

  .liquidity-metric__value {
    font-size: 28px;
  }
}

/* ============================================================
   2. 布局重置
   ============================================================ */
.explore-page {
  min-height: 100vh;
  background: var(--bg-page);
}

/* ============================================================
   3. 顶部导航
   ============================================================ */

/* ============================================================
   4. 温度仪表盘
   ============================================================ */
.temperature-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1280px;
  padding: var(--space-standard) 24px 16px;
  margin: 0 auto;
}

/* 探市「综合温度」卡内的进度条与跳转提示（来自 TemperatureGaugeCard 的 footer 插槽，属父组件作用域） */
.primary-bar {
  height: 3px;
  overflow: hidden;
  background: var(--bg-soft);
  border-radius: 2px;
}

.primary-fill {
  height: 100%;
  border-radius: 2px;
  transition:
    width 0.8s ease,
    background 0.6s ease;
}

.primary-link {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-primary);
  white-space: nowrap;
  cursor: pointer;
}

/* ---- 4.2 分组指标区：情绪/估值两列等宽，流动性独占一行 ---- */
.metrics-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 16px;

  &--single {
    grid-template-columns: 1fr;
  }
}

.metrics-group {
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.liquidity-block {
  display: flex;
  flex-direction: column;
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.liquidity-card {
  display: flex;
  flex-direction: row;
  gap: 24px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px;
  margin-top: 4px;
}

.liquidity-metric {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
  text-align: left;

  &__label {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  &__body {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: baseline;
  }

  &__value {
    font-family: var(--font-mono);
    font-size: 42px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    color: var(--text-primary);
  }

  &__unit {
    font-size: 16px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  &__hint {
    font-size: 12px;
    color: var(--text-tertiary);
  }
}

.liquidity-divider {
  flex-shrink: 0;
  width: 1px;
  height: 64px;
  background: var(--border-light);
}

.liquidity-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 120px;
}

.liquidity-btn {
  justify-content: flex-start;
  padding: 0;
  font-size: 13px;
  color: var(--text-secondary);

  &:hover {
    color: var(--brand-700);
  }
}

/* ---- 4.3 指数快照 ---- */
.index-snapshot {
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.snapshot-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.snapshot-items {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
}

.snapshot-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.snapshot-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.snapshot-price {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.snapshot-change {
  font-size: 13px;
}

/* ============================================================
   5. 添加/观察栏
   ============================================================ */

/* ============================================================
   6. 观察列表
   ============================================================ */
.watchlist-section {
  max-width: 1280px;
  padding: 0 24px 24px;
  margin: 0 auto;
}

.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 16px;

  .summary-left {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .summary-count {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .summary-divider {
    color: var(--border-default);
  }

  .summary-value {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .summary-pnl {
    font-size: 14px;
  }

  .summary-hint {
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .summary-right {
    display: flex;
    gap: 12px;
    align-items: center;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .refresh-interval-select {
    width: 96px;
  }

  .status-indicator {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &.status-trading {
      background: var(--color-rise);
      animation: pulse 1.5s infinite;
    }

    &.status-closed {
      background: var(--text-tertiary);
    }

    &.status-error {
      background: var(--color-danger-system);
      animation: pulse 1s infinite;
    }

    &.status-idle {
      background: var(--text-disabled);
    }
  }

  .update-time {
    font-size: 12px;
    color: var(--text-tertiary);
  }
}

/* ============================================================
   1. 设计 Token
   温度三色(--temp-*) 已在全局 colors.css 中定义，此处直接复用，不重复声明
   ============================================================ */
</style>
