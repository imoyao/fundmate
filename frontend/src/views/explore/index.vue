<!-- frontend/src/views/explore/index.vue -->
<template>
  <div class="explore-page">
    <!-- ===== 顶部导航（公共组件，与温度计完全一致） ===== -->
    <MarketHeader :logo="MARKET_LOGO" badge="探市" :navs="headerNavs" />

    <!-- ============================================================ -->
    <!-- 温度数据仪表盘                                                -->
    <!-- ============================================================ -->
    <section class="temperature-dashboard">
      <!-- 综合温度 + 恐惧贪婪 + 股债性价比（比例 2:1:1） -->
      <MetricGrid>
        <!-- 综合温度 -->
        <TemperatureGaugeCard
          class="gauge-card--featured"
          :value="compositeTemperature?.value ?? null"
          title="综合温度"
          :level="compositeTemperature?.level || '暂无'"
          caption="综合6个市场指标"
          size="sm"
          clickable
          @click="goToTemperature"
        >
          <template #footer>
            <div class="primary-bar">
              <div
                class="primary-fill"
                :style="{
                  width:
                    (compositeTemperature?.value != null
                      ? Math.max(0, Math.min(100, compositeTemperature.value))
                      : 0) + '%',
                  background: progressColor
                }"
              />
            </div>
            <span class="primary-link">查看温度计 ›</span>
          </template>
        </TemperatureGaugeCard>

        <!-- 恐惧贪婪 -->
        <MetricCard
          title="恐惧贪婪"
          :value="fearData ? fearData.value : null"
          :level="fearData?.label || '暂无数据'"
        />

        <!-- 股债性价比 -->
        <MetricCard
          title="股债性价比"
          :value="selfCalcPercent != null ? selfCalcPercent : null"
          unit="%"
          :level="selfCalcLevel"
        />
      </MetricGrid>

      <!-- L2：市场情绪 + 估值指标（两列等宽，避免重心偏左） -->
      <div class="metrics-row">
        <!-- 市场情绪 -->
        <div class="metrics-group metrics-group--half">
          <SectionHeader title="市场情绪" />
          <MetricGrid>
            <MetricCard
              title="且慢"
              :value="qiemanData ? qiemanData.value : null"
              unit="°"
              :level="qiemanData?.label || '暂无'"
            />
            <MetricCard
              title="有知有行"
              :value="youzhiData ? youzhiData.value : null"
              unit="°"
              :level="youzhiData?.label || '暂无'"
            />
            <MetricCard
              title="韭圈儿中长期"
              :value="jiucaishuoMediumData ? jiucaishuoMediumData.value : null"
              unit="°"
              :level="jiucaishuoMediumData?.label || '暂无'"
            />
          </MetricGrid>
        </div>

        <!-- 估值指标 -->
        <div class="metrics-group metrics-group--half">
          <SectionHeader title="估值指标" />
          <MetricGrid>
            <MetricCard
              title="中位PB"
              :value="jisiluIndicator?.median_pb ?? null"
              unit="倍"
              :level="pbLevel"
              :caption="pbCaption"
            />
            <MetricCard
              title="中位PE"
              :value="jisiluIndicator?.median_pe ?? null"
              unit="倍"
              :level="peLevel"
              :caption="peCaption"
            />
            <MetricCard
              title="可转债"
              :value="cbTemperature != null ? cbTemperature : null"
              unit="°"
              :level="cbLabel || '暂无'"
            />
          </MetricGrid>
        </div>
      </div>

      <!-- L3：流动性（独占一行，横向大卡片，信息更聚焦） -->
      <div class="metrics-row metrics-row--single">
        <div class="liquidity-block">
          <SectionHeader title="流动性" />
          <div class="liquidity-card">
            <div class="liquidity-metric">
              <span class="liquidity-metric__label">今日成交额</span>
              <div class="liquidity-metric__body">
                <span class="liquidity-metric__value">{{
                  volumeData ? volumeData.value : "--"
                }}</span>
                <span class="liquidity-metric__unit">亿</span>
                <TemperatureLevelBadge
                  :level="volumeData?.label || '暂无'"
                  size="sm"
                />
              </div>
              <span class="liquidity-metric__hint"
                >成交量热度反映市场活跃度</span
              >
            </div>
            <div class="liquidity-divider" />
            <div class="liquidity-actions">
              <el-button
                link
                class="liquidity-btn"
                @click="handleShowIndustryCrowding"
                >行业拥挤度 →</el-button
              >
              <el-button
                link
                class="liquidity-btn"
                @click="handleShowSectorFlow"
                >板块资金流 →</el-button
              >
            </div>
          </div>
        </div>
      </div>

      <!-- 指数快照（独立一行） -->
      <div class="index-snapshot">
        <div class="snapshot-title">指数快照</div>
        <div class="snapshot-items">
          <div v-for="idx in indexData" :key="idx.code" class="snapshot-item">
            <span class="snapshot-name">{{ idx.name }}</span>
            <span class="snapshot-price">{{ idx.price }}</span>
            <span class="snapshot-change"
              ><RiseFallText :value="idx.changePercent"
            /></span>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================================================ -->
    <!-- 添加/观察栏                                                   -->
    <!-- ============================================================ -->
    <section id="add-section" class="add-section">
      <div class="add-card">
        <div class="add-form-row">
          <div class="input-wrapper">
            <el-autocomplete
              v-model="newAsset.symbol"
              :fetch-suggestions="querySearch"
              placeholder="输入代码或名称搜索（如 510300）"
              size="large"
              clearable
              :trigger-on-focus="false"
              class="symbol-input"
              @select="handleSelect"
              @input="() => {}"
              @keyup.enter="handleAdd"
            >
              <template #prefix>
                <span class="input-prefix">搜索</span>
              </template>
              <template #default="{ item }">
                <div class="suggestion-item">
                  <span class="suggestion-code">{{ item.code }}</span>
                  <span class="suggestion-name">{{ item.name }}</span>
                  <el-tag size="small" class="suggestion-tag">{{
                    getTypeLabel(item.type)
                  }}</el-tag>
                </div>
              </template>
            </el-autocomplete>
          </div>

          <el-select
            v-model="newAsset.type"
            placeholder="类型"
            size="large"
            class="type-select"
          >
            <el-option label="股票" value="stock" />
            <el-option label="基金" value="fund" />
            <el-option label="ETF" value="etf" />
          </el-select>

          <el-input
            v-model="newAsset.costPriceInput"
            placeholder="成本价（选填）"
            size="large"
            class="price-input"
            clearable
          >
            <template #prepend>¥</template>
          </el-input>

          <el-input
            v-model="newAsset.quantityInput"
            placeholder="份额（选填）"
            size="large"
            class="qty-input"
            clearable
          />

          <el-button
            type="primary"
            size="large"
            :loading="adding"
            @click="handleAdd"
            >添加观察</el-button
          >
        </div>

        <div class="hot-section">
          <span class="hot-label">热门资产</span>
          <div class="hot-cards">
            <div
              v-for="item in hotAssets"
              :key="item.symbol"
              class="hot-card"
              @click="addHotAsset(item)"
            >
              <span class="hot-name">{{ item.name }}</span>
              <span class="hot-code">{{ item.symbol }}</span>
            </div>
          </div>
        </div>
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
          <span v-if="lastUpdateTime" class="update-time"
            >更新: {{ lastUpdateTime }}</span
          >
          <el-button size="small" @click="manualRefresh">刷新</el-button>
        </div>
      </div>

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
      copyright="© 2026 多倍贝 · 让投资更从容"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { useLocalHoldings } from "@/composables/useLocalHoldings";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { useAssetSearch } from "@/composables/useAssetSearch";
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
import { getTemperatureOverview } from "@/api/temperature";

defineOptions({
  name: "ExplorePage"
});

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
// 指数数据
// ================================================================
interface IndexInfo {
  code: string;
  name: string;
  price: string;
  changePercent: number;
}

const indexCodes = [
  { symbol: "000300", type: "stock" as const },
  { symbol: "000905", type: "stock" as const },
  { symbol: "399006", type: "stock" as const }
];

const indexData = ref<IndexInfo[]>([
  { code: "000300", name: "沪深300", price: "--", changePercent: 0 },
  { code: "000905", name: "中证500", price: "--", changePercent: 0 },
  { code: "399006", name: "创业板指", price: "--", changePercent: 0 }
]);

const indexLoading = ref(false);

const fetchIndexData = async () => {
  indexLoading.value = true;
  try {
    const result = await batchFetchQuotes(indexCodes);
    indexData.value = indexData.value.map(idx => {
      const quote = result.get(idx.code);
      if (quote) {
        const price = quote.currentPrice || 0;
        const change = quote.changePct || 0;
        return {
          ...idx,
          price: price > 0 ? price.toFixed(2) : "--",
          changePercent: change
        };
      }
      return idx;
    });
  } catch {
    // 静默失败
  } finally {
    indexLoading.value = false;
  }
};

// ================================================================
// 市场温度数据
// ================================================================
const tempLoading = ref(false);

// 综合温度（后端两源合成，当前占位）
const compositeTemperature = ref<{ value: number; level: string } | null>(null);

// 综合温度进度条颜色：按温度档位取色，偏低时为绿色
const progressColor = computed(() => {
  const v = compositeTemperature.value?.value;
  if (v == null || Number.isNaN(v)) return "var(--temp-mid)";
  if (v < 40) return "var(--temp-low)";
  if (v > 60) return "var(--temp-high)";
  return "var(--temp-mid)";
});

// 根据估值温度推断等级（PB/PE 温度越低代表估值越便宜）
const inferValuationLevel = (
  temperature: number | null | undefined
): string => {
  if (temperature == null || Number.isNaN(temperature)) return "暂无";
  if (temperature < 30) return "偏低";
  if (temperature > 70) return "偏高";
  return "适中";
};

const pbLevel = computed(() =>
  inferValuationLevel(jisiluIndicator.value?.median_pb_temperature)
);
const peLevel = computed(() =>
  inferValuationLevel(jisiluIndicator.value?.median_pe_temperature)
);

const pbCaption = computed(() => {
  const temp = jisiluIndicator.value?.median_pb_temperature;
  if (temp == null) return "估值温度 --";
  return `估值温度 ${temp}° · 越低越便宜`;
});

const peCaption = computed(() => {
  const temp = jisiluIndicator.value?.median_pe_temperature;
  if (temp == null) return "估值温度 --";
  return `估值温度 ${temp}° · 越低越便宜`;
});

// 自算·股债利差（不涉 PE）
const selfCalcPercent = ref<number | null>(null);
const selfCalcLevel = ref<string>("数据暂缺");

// 来源链接（底部来源条）
const links = ref<Record<string, string>>({});

// 成交量
const volumeData = ref<{ value: number; label: string } | null>(null);

// L2 温度数据
const fearData = ref<{ value: number; label: string } | null>(null);
const jiucaishuoMediumData = ref<{ value: number; label: string } | null>(null);
const qiemanData = ref<{ value: number; label: string } | null>(null);
const youzhiData = ref<{ value: number; label: string } | null>(null);
const cbTemperature = ref<number | null>(null);
const cbLabel = ref<string>("");
const jisiluIndicator = ref<{
  median_pb: number;
  median_pb_temperature: number;
  median_pb_level?: string;
  median_pe: number;
  median_pe_temperature: number;
  median_pe_level?: string;
} | null>(null);

const fetchTemperature = async () => {
  tempLoading.value = true;
  try {
    const res = await getTemperatureOverview();
    const data = res.data;
    if (!data) throw new Error("无效响应");

    // 自算·股债利差（不涉 PE）
    const selfCalc = data.composites?.self_calc;
    if (selfCalc) {
      selfCalcPercent.value = selfCalc.percent ?? null;
      selfCalcLevel.value = selfCalc.level ?? "暂无";
    } else {
      selfCalcLevel.value = "数据暂缺";
    }

    // 综合温度（两源合成）
    compositeTemperature.value = data.composites?.composite_temperature || null;

    // 来源链接
    links.value = data.links || {};

    // 成交量
    const vol = data.singles?.find((s: any) => s.source === "eastmoney_volume");
    if (vol) {
      volumeData.value = {
        value: vol.value,
        label: vol.label || "温和"
      };
    }

    // L2：各类温度数据
    const singles = data.singles || [];

    const fear = singles.find((s: any) => s.source === "jiucaishuo_fear");
    if (fear) {
      fearData.value = { value: fear.value, label: fear.label };
    }

    const medium = singles.find((s: any) => s.source === "jiucaishuo_medium");
    if (medium) {
      jiucaishuoMediumData.value = { value: medium.value, label: medium.label };
    }

    const qieman = singles.find((s: any) => s.source === "qieman");
    if (qieman) {
      qiemanData.value = { value: qieman.value, label: qieman.label };
    }

    const youzhi = singles.find((s: any) => s.source === "youzhiyouxing");
    if (youzhi) {
      youzhiData.value = { value: youzhi.value, label: youzhi.label };
    }

    const cb = singles.find((s: any) => s.source === "jisilu_cb");
    if (cb) {
      cbTemperature.value = cb.value;
      cbLabel.value = cb.label || "";
    }

    const indicator = data.composites?.jisilu_indicator;
    if (indicator) {
      jisiluIndicator.value = {
        median_pb: indicator.median_pb,
        median_pb_temperature: indicator.median_pb_temperature,
        median_pb_level: indicator.median_pb_level,
        median_pe: indicator.median_pe,
        median_pe_temperature: indicator.median_pe_temperature,
        median_pe_level: indicator.median_pe_level
      };
    }

    if (selfCalcLevel.value === "数据暂缺") {
      console.warn("自算股债利差数据暂缺，显示占位");
    }
  } catch (error) {
    console.warn("获取市场温度失败:", error);
    selfCalcLevel.value = "数据暂缺";
  } finally {
    tempLoading.value = false;
  }
};

// ================================================================
// 计算属性和方法
// ================================================================

// L3 深度入口
const handleShowIndustryCrowding = () => {
  ElMessage.info("行业拥挤度功能开发中");
};

const handleShowSectorFlow = () => {
  ElMessage.info("板块资金流功能开发中");
};

// ================================================================
// 搜索（复用 useAssetSearch）
// ================================================================
const {
  loading: searchLoading,
  results: searchResults,
  search
} = useAssetSearch();

const querySearch = (queryString: string, cb: (results: any[]) => void) => {
  search(queryString, cb);
};

// ================================================================
// 新资产表单
// ================================================================
const adding = ref(false);
const selectedAssetInfo = ref<any>(null);

const newAsset = reactive({
  symbol: "",
  type: "stock" as "stock" | "fund" | "etf",
  costPriceInput: "",
  quantityInput: ""
});

const handleSelect = (item: any) => {
  if (!item || !item.code) return;
  newAsset.symbol = item.code;
  newAsset.type = item.type || "stock";
  selectedAssetInfo.value = item;
  const quote = quotesMap.value?.[item.code];
  if (quote?.currentPrice) {
    newAsset.costPriceInput = String(quote.currentPrice);
  }
  if (!newAsset.quantityInput) {
    newAsset.quantityInput = "1";
  }
};

const handleAdd = async () => {
  const symbol = newAsset.symbol.trim();
  if (!symbol) {
    ElMessage.warning("请输入资产代码");
    return;
  }

  const costPrice = newAsset.costPriceInput
    ? parseFloat(newAsset.costPriceInput)
    : null;
  const quantity = newAsset.quantityInput
    ? parseFloat(newAsset.quantityInput)
    : null;

  if (costPrice !== null && isNaN(costPrice)) {
    ElMessage.warning("请输入有效的成本价");
    return;
  }
  if (quantity !== null && isNaN(quantity)) {
    ElMessage.warning("请输入有效的份额");
    return;
  }

  let name = selectedAssetInfo.value?.name;
  if (!name) {
    const found = searchResults.value.find(item => item.code === symbol);
    name = found?.name || symbol;
  }

  adding.value = true;
  try {
    const result = addHolding({
      symbol,
      name,
      type: newAsset.type,
      costPrice: costPrice ?? null,
      quantity: quantity ?? null
    });
    if (!result.success) {
      ElMessage.warning(result.message);
    } else {
      ElMessage.success(`已添加「${name}」到观察列表`);
      newAsset.symbol = "";
      newAsset.type = "stock";
      newAsset.costPriceInput = "";
      newAsset.quantityInput = "";
      selectedAssetInfo.value = null;
    }
  } catch (e) {
    console.error("添加失败:", e);
    ElMessage.error("添加失败，请重试");
  } finally {
    adding.value = false;
  }
};

// ================================================================
// 热门预置
// ================================================================
// 热门预置只提供「标的 + 类型」，不预填成本价/份额。
// 传 null 即进入纯观察模式（useLocalHoldings 约定：costPrice/quantity 为 null = 未填），
// 由系统按当前价取成本、份额 1，盈亏恒为 0，避免展示编造的持仓收益（原 P0-2 硬编码假数据）。
const hotAssets = [
  { symbol: "510300", name: "沪深300ETF", type: "etf" as const },
  { symbol: "513100", name: "纳指ETF", type: "etf" as const },
  { symbol: "600036", name: "招商银行", type: "stock" as const },
  { symbol: "588000", name: "科创50ETF", type: "etf" as const }
];

const addHotAsset = (item: (typeof hotAssets)[0]) => {
  try {
    const result = addHolding({
      symbol: item.symbol,
      name: item.name,
      type: item.type,
      costPrice: null,
      quantity: null
    });
    if (!result.success) {
      ElMessage.warning(result.message);
    } else {
      ElMessage.success(`已添加「${item.name}」到观察列表（纯观察，未填成本）`);
    }
  } catch (e) {
    console.error(e);
    ElMessage.error("添加失败");
  }
};

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
// 基金/ETF 最新价为净值，展示 4 位小数；其余证券 2 位
const pricePrecision = (type: string): number =>
  type === "fund" || type === "etf" ? 4 : 2;

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
// 工具方法
// ================================================================
const getTypeLabel = (type: string): string => {
  const map: Record<string, string> = {
    stock: "股票",
    etf: "ETF",
    fund: "场外基金",
    bond: "可转债",
    index: "指数"
  };
  return map[type] || type;
};

// ================================================================
// 页面方法
// ================================================================
const goToTemperature = () => {
  router.push("/temperature");
};

// ================================================================
// Header / Footer 公共组件数据
// ================================================================
const headerNavs = useMarketHeaderNavs();

const footerSources = computed(() => buildMarketFooterSources(links.value));

// ================================================================
// 生命周期
// ================================================================
onMounted(() => {
  if (!enabled.value) {
    toggle(true);
  }
  fetchIndexData();
  fetchTemperature();
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
.add-section {
  max-width: 1280px;
  padding: 16px 24px 8px;
  margin: 0 auto;
}

.add-card {
  padding: 20px 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.add-form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;

  .input-wrapper {
    flex: 2;
    min-width: 200px;
  }

  .symbol-input {
    width: 100%;
  }

  .type-select {
    flex-shrink: 0;
    width: 120px;
  }

  .price-input {
    flex-shrink: 0;
    width: 140px;
  }

  .qty-input {
    flex-shrink: 0;
    width: 120px;
  }
}

.input-prefix {
  font-size: 13px;
  color: var(--text-tertiary);
}

.suggestion-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 4px 0;

  .suggestion-code {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .suggestion-name {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .suggestion-tag {
    margin-left: auto;
    font-size: 11px;
  }
}

.hot-section {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--border-light);

  .hot-label {
    font-size: 13px;
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  .hot-cards {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .hot-card {
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 4px 14px;
    font-size: 13px;
    cursor: pointer;
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    border-radius: 20px;
    transition: all 0.2s;

    &:hover {
      background: var(--brand-100);
      border-color: var(--brand-400);
      transform: translateY(-1px);
    }

    .hot-name {
      color: var(--text-primary);
    }

    .hot-code {
      font-size: 11px;
      color: var(--text-tertiary);
    }
  }
}

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
