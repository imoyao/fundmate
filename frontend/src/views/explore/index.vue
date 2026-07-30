<!-- frontend/src/views/explore/index.vue -->
<template>
  <div class="explore-page">
    <!-- ===== 顶部导航 ===== -->
    <header class="explore-header">
      <div class="header-inner">
        <div class="logo-area">
          <span class="logo">ShowBuy</span>
          <span class="badge">探市 · 研究</span>
        </div>
        <div class="nav-actions">
          <el-button link @click="showWhyModal">为什么选 ShowBuy</el-button>
          <el-button type="primary" size="small" @click="scrollToAdd">开始体验 ↓</el-button>
          <el-button type="primary" @click="goToRegister">立即注册 →</el-button>
        </div>
      </div>
    </header>

    <!-- ============================================================ -->
    <!-- 温度数据卡片网格                                              -->
    <!-- ============================================================ -->
    <section class="temperature-grid">
      <!-- 一级锚点区（不等宽 2:1:1） -->
      <!-- 综合温度（hero，占位占最大块） -->
      <div class="temp-card temp-card-main temp-card-hero">
        <div class="temp-card-header">
          <span class="temp-card-title">综合温度</span>
          <span class="temp-card-badge badge-dev">占位</span>
        </div>
        <div class="temp-card-body">
          <span class="temp-card-value">{{ compositeTemperature?.value != null ? compositeTemperature.value : '--' }}</span>
          <span class="temp-card-label" :class="compositeLevelClass">{{ compositeTemperature?.level || '算法开发中' }}</span>
        </div>
        <div class="temp-card-bar">
          <div class="temp-card-track">
            <div class="temp-card-fill" :style="{ width: (compositeTemperature?.value != null ? Math.max(0, Math.min(100, compositeTemperature.value)) : 0) + '%' }" />
          </div>
        </div>
        <div class="temp-card-footer">
          <span>加权参考 ⊕ 自算·股债利差（合成中）</span>
        </div>
      </div>

      <!-- 恐惧贪婪指数 -->
      <div class="temp-card temp-card-anchor">
        <div class="temp-card-header">
          <span class="temp-card-title">恐惧贪婪指数</span>
        </div>
        <div class="temp-card-body">
          <span class="temp-card-value">{{ fearData ? fearData.value : '--' }}</span>
          <span class="temp-card-label" :class="getFearClass(fearData?.label)">{{ fearData?.label || '数据暂缺' }}</span>
        </div>
      </div>

      <!-- 自算·股债利差 -->
      <div class="temp-card temp-card-anchor">
        <div class="temp-card-header">
          <span class="temp-card-title">自算·股债利差</span>
        </div>
        <div class="temp-card-body">
          <span class="temp-card-value">{{ selfCalcPercent != null ? selfCalcPercent : '--' }}<span class="temp-card-unit">%</span></span>
          <span class="temp-card-label" :class="selfCalcLevelClass">{{ selfCalcLevel }}</span>
        </div>
        <div class="temp-card-footer">
          <span>股债利差 · 不涉 PE</span>
        </div>
      </div>

      <!-- 二级 · 市场情绪 -->
      <div class="temp-group">
        <div class="temp-group-title">市场情绪</div>
        <div class="temp-group-cards">
          <div class="temp-card">
            <div class="temp-card-header"><span class="temp-card-title">韭圈儿中长期</span></div>
            <div class="temp-card-body">
              <span class="temp-card-value">{{ jiucaishuoMediumData ? jiucaishuoMediumData.value : '--' }}</span>
              <span class="temp-card-label">{{ jiucaishuoMediumData?.label || '数据暂缺' }}</span>
            </div>
          </div>
          <div class="temp-card">
            <div class="temp-card-header"><span class="temp-card-title">且慢</span></div>
            <div class="temp-card-body">
              <span class="temp-card-value">{{ qiemanData ? qiemanData.value : '--' }}</span>
              <span class="temp-card-label">{{ qiemanData?.label || '数据暂缺' }}</span>
            </div>
          </div>
          <div class="temp-card">
            <div class="temp-card-header"><span class="temp-card-title">有知有行</span></div>
            <div class="temp-card-body">
              <span class="temp-card-value">{{ youzhiData ? youzhiData.value : '--' }}</span>
              <span class="temp-card-label">{{ youzhiData?.label || '数据暂缺' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 二级 · 估值与专项 -->
      <div class="temp-group">
        <div class="temp-group-title">估值与专项</div>
        <div class="temp-group-cards">
          <div class="temp-card">
            <div class="temp-card-header"><span class="temp-card-title">全市场估值</span></div>
            <div class="temp-card-body">
              <div class="temp-card-row">
                <span class="temp-card-key">中位PB</span>
                <span class="temp-card-value-sm">{{ jisiluIndicator?.median_pb ?? '--' }}</span>
                <span class="temp-card-temp">{{ jisiluIndicator?.median_pb_temperature ?? '--' }}%</span>
              </div>
              <div class="temp-card-row">
                <span class="temp-card-key">中位PE</span>
                <span class="temp-card-value-sm">{{ jisiluIndicator?.median_pe ?? '--' }}</span>
                <span class="temp-card-temp">{{ jisiluIndicator?.median_pe_temperature ?? '--' }}%</span>
              </div>
            </div>
          </div>
          <div class="temp-card">
            <div class="temp-card-header"><span class="temp-card-title">可转债</span></div>
            <div class="temp-card-body">
              <span class="temp-card-value">{{ cbTemperature != null ? cbTemperature : '--' }}</span>
              <span class="temp-card-unit">%</span>
              <span class="temp-card-label" :class="cbLabel === '偏高' ? 'label-high' : cbLabel === '偏低' ? 'label-low' : 'label-mid'">{{ cbLabel || '数据暂缺' }}</span>
            </div>
          </div>
          <div class="temp-card temp-card-index">
            <div class="temp-card-header"><span class="temp-card-title">指数快照</span></div>
            <div class="temp-card-body">
              <div v-for="idx in indexData" :key="idx.code" class="temp-card-row">
                <span class="temp-card-key">{{ idx.name }}</span>
                <span class="temp-card-value-sm">{{ idx.price }}</span>
                <span class="temp-card-change"><RiseFallText :value="idx.changePercent" /></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 二级 · 流动性 -->
      <div class="temp-group">
        <div class="temp-group-title">流动性</div>
        <div class="temp-group-cards">
          <div class="temp-card">
            <div class="temp-card-header"><span class="temp-card-title">成交额</span></div>
            <div class="temp-card-body">
              <span class="temp-card-value">{{ volumeData ? volumeData.value : '--' }}</span>
              <span class="temp-card-unit">亿</span>
              <span class="temp-card-label" :class="volumeData?.label === '放量' ? 'label-high' : volumeData?.label === '缩量' ? 'label-low' : 'label-mid'">{{ volumeData?.label || '数据暂缺' }}</span>
            </div>
          </div>
          <div class="temp-card temp-card-entry">
            <div class="temp-card-header"><span class="temp-card-title">深度分析</span></div>
            <div class="temp-card-body">
              <el-button type="text" class="entry-btn" @click="handleShowIndustryCrowding">行业拥挤度 →</el-button>
              <el-button type="text" class="entry-btn" @click="handleShowSectorFlow">板块资金流 →</el-button>
            </div>
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
              @select="handleSelect"
              @input="() => {}"
              @keyup.enter="handleAdd"
              class="symbol-input"
            >
              <template #prefix>
                <span class="input-prefix">搜索</span>
              </template>
              <template #default="{ item }">
                <div class="suggestion-item">
                  <span class="suggestion-code">{{ item.code }}</span>
                  <span class="suggestion-name">{{ item.name }}</span>
                  <el-tag size="small" class="suggestion-tag">{{ getTypeLabel(item.type) }}</el-tag>
                </div>
              </template>
            </el-autocomplete>
          </div>

          <el-select v-model="newAsset.type" placeholder="类型" size="large" class="type-select">
            <el-option label="股票" value="stock" />
            <el-option label="基金" value="fund" />
            <el-option label="ETF" value="etf" />
          </el-select>

          <el-input v-model="newAsset.costPriceInput" placeholder="成本价（选填）" size="large" class="price-input" clearable>
            <template #prepend>¥</template>
          </el-input>

          <el-input v-model="newAsset.quantityInput" placeholder="份额（选填）" size="large" class="qty-input" clearable />

          <el-button type="primary" size="large" :loading="adding" @click="handleAdd">添加观察</el-button>
        </div>

        <div class="hot-section">
          <span class="hot-label">热门资产</span>
          <div class="hot-cards">
            <div v-for="item in hotAssets" :key="item.symbol" class="hot-card" @click="addHotAsset(item)">
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
            <span class="summary-value">总市值 <MoneyDisplay :value="summary.totalMarketValue" :show-sign="false" /></span>
            <span class="summary-divider">|</span>
            <span class="summary-pnl">盈亏 <RiseFallText :value="summary.totalPnl" suffix="" /></span>
          </template>
          <span v-if="isPureObservationMode" class="summary-hint">输入成本与份额后可查看持仓盈亏</span>
        </div>
        <div class="summary-right">
          <span class="status-indicator">
            <span class="status-dot" :class="statusClass" />{{ statusText }}
          </span>
          <span v-if="lastUpdateTime" class="update-time">更新: {{ lastUpdateTime }}</span>
          <el-button size="small" @click="manualRefresh">刷新</el-button>
        </div>
      </div>

      <el-table :data="tableData" border style="width:100%" v-loading="loading" empty-text="暂无观察资产，添加你关注的标的开始研究">
        <el-table-column label="产品" min-width="180">
          <template #default="{ row }">
            <ProductDisplay :name="row.name" :symbol="row.symbol" :type-label="getTypeLabel(row.type)" />
          </template>
        </el-table-column>

        <el-table-column label="最新价" width="120" align="right">
          <template #default="{ row }"><MoneyDisplay :value="row.price" :show-sign="false" /></template>
        </el-table-column>

        <el-table-column label="涨跌幅" width="110" align="right">
          <template #default="{ row }"><RiseFallText :value="row.changePct" /></template>
        </el-table-column>

        <el-table-column v-if="!isPureObservationMode" label="当日盈亏" width="130" align="right">
          <template #default="{ row }"><MoneyDisplay :value="row.pnl ?? 0" :show-sign="true" /></template>
        </el-table-column>

        <el-table-column v-if="!isPureObservationMode" label="持仓收益" width="130" align="right">
          <template #default="{ row }"><MoneyDisplay :value="row.positionPnl ?? 0" :show-sign="true" /></template>
        </el-table-column>

        <el-table-column label="深度分析" width="120" align="center">
          <template #default="{ row }">
            <el-dropdown @command="handleJump(row, $event)">
              <el-button size="small" type="primary" plain>分析 ▼</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="tool in getAvailableTools(row.type)" :key="tool.key" :command="tool.key">
                    {{ tool.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button type="text" size="small" style="color:var(--text-tertiary)" @click="handleRemove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ============================================================ -->
    <!-- 底部：数据来源 + 免责声明                                     -->
    <!-- ============================================================ -->
    <footer class="footer-section">
      <div class="footer-inner">
        <div class="footer-legend">
          <span class="legend-item"><span class="legend-dot legend-low"></span>绿=低温·机会区</span>
          <span class="legend-item"><span class="legend-dot legend-high"></span>红=高温·谨慎区</span>
          <span class="legend-item"><span class="legend-dot legend-mid"></span>金=适中·平稳</span>
          <span class="legend-note">温度色与观察列表「红涨绿跌」相互独立</span>
        </div>
        <div class="footer-sources">
          <span class="footer-label">数据来源：</span>
          <a v-if="links.jiucaishuo" class="footer-source" :href="links.jiucaishuo" target="_blank" rel="noopener">韭圈儿</a>
          <a v-if="links.jisilu" class="footer-source" :href="links.jisilu" target="_blank" rel="noopener">集思录</a>
          <a v-if="links.eastmoney" class="footer-source" :href="links.eastmoney" target="_blank" rel="noopener">东方财富</a>
          <a v-if="links.qieman" class="footer-source" :href="links.qieman" target="_blank" rel="noopener">且慢</a>
          <a v-if="links.youzhiyouxing" class="footer-source" :href="links.youzhiyouxing" target="_blank" rel="noopener">有知有行</a>
          <span class="footer-source footer-source-self">自算·股债利差</span>
          <span class="footer-source footer-source-dev">行业拥挤度（开发中）</span>
          <span class="footer-source footer-source-dev">板块资金流（开发中）</span>
        </div>
        <div class="footer-disclaimer">
          <span class="footer-disclaimer-text">
            综合温度基于多源数据加权计算，算法仍在优化中，当前为占位展示。
            所有数据仅为市场信息参考，不构成任何投资建议。投资有风险，决策需谨慎。
          </span>
        </div>
        <div class="footer-copyright">© 2026 ShowBuy · 让投资更从容</div>
      </div>
    </footer>
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
  (newHoldings) => {
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
    indexData.value = indexData.value.map((idx) => {
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
  median_pe: number;
  median_pe_temperature: number;
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
      selfCalcLevel.value = selfCalc.level || "正常";
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
        median_pe: indicator.median_pe,
        median_pe_temperature: indicator.median_pe_temperature
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
const selfCalcLevelClass = computed(() => {
  const level = selfCalcLevel.value;
  if (level === "偏低" || level === "低估") return "label-low";
  if (level === "偏高" || level === "高估") return "label-high";
  return "label-mid";
});

const compositeLevelClass = computed(() => {
  const level = compositeTemperature.value?.level;
  if (level === "偏低" || level === "低估") return "label-low";
  if (level === "偏高" || level === "高估") return "label-high";
  return "label-mid";
});

const getFearClass = (label: string | undefined) => {
  if (!label) return "label-mid";
  if (label.includes("极度恐惧") || label.includes("恐惧")) return "label-low";
  if (label.includes("极度贪婪") || label.includes("贪婪")) return "label-high";
  return "label-mid";
};

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
const { loading: searchLoading, results: searchResults, search } = useAssetSearch();

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

  const costPrice = newAsset.costPriceInput ? parseFloat(newAsset.costPriceInput) : null;
  const quantity = newAsset.quantityInput ? parseFloat(newAsset.quantityInput) : null;

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
    const found = searchResults.value.find((item) => item.code === symbol);
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
const hotAssets = [
  { symbol: "510300", name: "沪深300ETF", type: "etf" as const, costPrice: 4.567, quantity: 100 },
  { symbol: "513100", name: "纳指ETF", type: "etf" as const, costPrice: 1.234, quantity: 100 },
  { symbol: "600036", name: "招商银行", type: "stock" as const, costPrice: 34.56, quantity: 100 },
  { symbol: "588000", name: "科创50ETF", type: "etf" as const, costPrice: 0.987, quantity: 100 }
];

const addHotAsset = (item: (typeof hotAssets)[0]) => {
  try {
    const result = addHolding({
      symbol: item.symbol,
      name: item.name,
      type: item.type,
      costPrice: item.costPrice,
      quantity: item.quantity
    });
    if (!result.success) {
      ElMessage.warning(result.message);
    } else {
      ElMessage.success(`已添加「${item.name}」到观察列表`);
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
    return hold.map((h) => {
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
const scrollToAdd = () => {
  document.getElementById("add-section")?.scrollIntoView({ behavior: "smooth" });
};

const loadDemoData = () => {
  hotAssets.forEach((item) => {
    try {
      addHolding({
        symbol: item.symbol,
        name: item.name,
        type: item.type,
        costPrice: item.costPrice,
        quantity: item.quantity
      });
    } catch {
      // ignore
    }
  });
  ElMessage.success("已加载演示数据");
};

const goToRegister = () => {
  router.push({ path: "/login", query: { from: "explore" } });
};

const showWhyModal = () => {
  ElMessage.info("ShowBuy：全资产记账 + 投资分析工具");
};

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
/* ===== 温度专用 token（临时补充，后续应迁移到 colors.css） ===== */
.explore-page {
  --temp-low: #4F9D69;
  --temp-mid: var(--tag-warm-sand, #D4C898);
  --temp-high: #D9534F;
  --temp-low-bg: rgba(79, 157, 105, 0.14);
  --temp-mid-bg: rgba(212, 200, 152, 0.20);
  --temp-high-bg: rgba(217, 83, 79, 0.14);
}

/* ===== 布局重置（清理旧样式） ===== */
.explore-page {
  min-height: 100vh;
  background: var(--bg-page);
}

/* ===== 顶部导航 ===== */
.explore-header {
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.7);
  border-bottom: 1px solid var(--border-light);

  .header-inner {
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 24px;
    height: 64px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .logo-area {
    display: flex;
    align-items: center;
    gap: 12px;

    .logo {
      font-weight: 700;
      font-size: 18px;
      color: var(--brand-700);
    }

    .badge {
      font-size: 12px;
      color: var(--text-secondary);
      background: var(--bg-soft);
      padding: 2px 10px;
      border-radius: 12px;
    }
  }

  .nav-actions {
    display: flex;
    align-items: center;
    gap: 16px;
  }
}

/* ===== 温度卡片网格 ===== */
.temperature-grid {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px 16px;
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

/* 一级锚点：综合温度(4份宽) + 恐惧贪婪 + 自算(各1份) */
.temp-card-hero {
  grid-column: span 4;
}
.temp-card-anchor {
  grid-column: span 1;
}

/* 二级：语义分组（整行容器 + 内部 6 列） */
.temp-group {
  grid-column: span 6;
}
.temp-group-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin: 8px 0 6px;
}
.temp-group-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}
.temp-group .temp-card {
  grid-column: span 2;
}

/* 卡片基础样式 */
.temp-card {
  background: var(--bg-card);
  border-radius: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  box-shadow: var(--shadow-raised);
  transition: all 0.2s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-float);
  }

  .temp-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }

  .temp-card-title {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-tertiary);
    letter-spacing: 0.3px;
  }

  .temp-card-body {
    display: flex;
    align-items: baseline;
    gap: 4px;
    flex-wrap: wrap;
  }

  .temp-card-value {
    font-size: 22px;
    font-weight: 700;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
  }

  .temp-card-value-sm {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  .temp-card-unit {
    font-size: 13px;
    color: var(--text-tertiary);
    margin-left: 0px;
  }

  .temp-card-label {
    font-size: 11px;
    padding: 1px 8px;
    border-radius: 8px;
    font-weight: 500;
    margin-left: auto;

    &.label-low {
      background: var(--temp-low-bg);
      color: var(--temp-low);
    }
    &.label-mid {
      background: var(--temp-mid-bg);
      color: var(--temp-mid);
    }
    &.label-high {
      background: var(--temp-high-bg);
      color: var(--temp-high);
    }
  }

  .temp-card-bar {
    margin-top: 6px;
  }

  .temp-card-track {
    height: 3px;
    border-radius: 2px;
    background: var(--bg-soft);
    overflow: hidden;
  }

  .temp-card-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(to right, var(--color-fall), var(--tag-warm-sand), var(--color-rise));
    transition: width 0.8s ease;
  }

  .temp-card-row {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 2px 0;

    .temp-card-key {
      font-size: 12px;
      color: var(--text-tertiary);
      min-width: 48px;
    }

    .temp-card-temp {
      font-size: 12px;
      font-weight: 500;
      color: var(--text-secondary);
      margin-left: auto;
    }

    .temp-card-change {
      font-size: 12px;
      margin-left: auto;
    }
  }

  .temp-card-badge {
    font-size: 9px;
    padding: 0 6px;
    border-radius: 4px;

    &.badge-dev {
      background: var(--brand-100);
      color: var(--brand-700);
    }
    &.badge-pending {
      background: var(--bg-soft);
      color: var(--text-tertiary);
    }
  }
}

/* 特殊卡片尺寸 */
.temp-card-main {
  grid-column: span 4;
  background: linear-gradient(135deg, var(--bg-card), var(--brand-100));
  border-color: var(--brand-400);

  .temp-card-value {
    font-size: 32px;
    color: var(--brand-700);
  }

  .temp-card-label {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .temp-card-footer {
    font-size: 10px;
    color: var(--text-tertiary);
    margin-top: 4px;
    width: 100%;
  }
}

.temp-card-index {
  grid-column: span 2;
}

.temp-card-entry {
  grid-column: span 1;

  .temp-card-body {
    flex-direction: column;
    gap: 4px;
  }

  .entry-btn {
    font-size: 13px;
    color: var(--text-secondary);
    padding: 2px 0;

    &:hover {
      color: var(--brand-700);
    }
  }
}

/* ===== 添加/观察栏 ===== */
.add-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px 24px 8px;
}

.add-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px 24px;
  box-shadow: var(--shadow-raised);
  border: 1px solid var(--border-light);
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
    width: 120px;
    flex-shrink: 0;
  }

  .price-input {
    width: 140px;
    flex-shrink: 0;
  }

  .qty-input {
    width: 120px;
    flex-shrink: 0;
  }
}

.input-prefix {
  font-size: 13px;
  color: var(--text-tertiary);
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;

  .suggestion-code {
    font-weight: 600;
    font-size: 14px;
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
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
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
    padding: 4px 14px;
    border-radius: 20px;
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 6px;

    &:hover {
      background: var(--brand-100);
      border-color: var(--brand-400);
      transform: translateY(-1px);
    }

    .hot-name {
      color: var(--text-primary);
    }

    .hot-code {
      color: var(--text-tertiary);
      font-size: 11px;
    }
  }
}

/* ===== 观察列表 ===== */
.watchlist-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px 24px;
}

.summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 16px;
  flex-wrap: wrap;
  gap: 8px;

  .summary-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
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
    align-items: center;
    gap: 12px;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;

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

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ===== 底部：数据来源 + 免责声明 ===== */
.footer-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px 24px 32px;
  border-top: 1px solid var(--border-light);
}

.footer-inner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.footer-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 16px;
  font-size: 12px;
  color: var(--text-secondary);
}
.legend-item {
  display: inline-flex;
  align-items: center;
}
.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 5px;
}
.legend-low { background: var(--temp-low); }
.legend-mid { background: var(--temp-mid); }
.legend-high { background: var(--temp-high); }
.legend-note {
  color: var(--text-tertiary);
  margin-left: 4px;
}

.footer-sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
}

.footer-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.footer-source {
  font-size: 12px;
  color: var(--text-secondary);

  &::before {
    content: "·";
    margin-right: 8px;
    color: var(--text-tertiary);
  }

  &:first-of-type::before {
    display: none;
  }

  &.footer-source-dev {
    color: var(--text-tertiary);
    font-style: italic;
  }
  &.footer-source-self {
    cursor: default;
  }
}

.footer-disclaimer-text {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.6;
}

.footer-copyright {
  font-size: 11px;
  color: var(--text-disabled);
}

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .temperature-grid {
    grid-template-columns: repeat(4, 1fr);
  }
  .temp-card-hero { grid-column: span 4; }
  .temp-card-anchor { grid-column: span 2; }
  .temp-group { grid-column: span 4; }
  .temp-card-index { grid-column: span 2; }
}

@media (max-width: 768px) {
  .temperature-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    padding: 0 16px 12px;
  }
  .temp-card { padding: 10px 12px; }
  .temp-card-hero,
  .temp-card-main,
  .temp-card-anchor {
    grid-column: span 2;
  }
  .temp-group { grid-column: span 2; }
  .temp-group-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .temp-group .temp-card { grid-column: span 1; }
  .temp-card-index { grid-column: span 2; }
  .temp-card-entry { grid-column: span 2; }
  .footer-sources { gap: 2px 8px; }
}

@media (max-width: 480px) {
  .temperature-grid {
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .temp-card-hero,
  .temp-card-main,
  .temp-card-anchor {
    grid-column: span 2;
  }
  .temp-card .temp-card-value {
    font-size: 18px;
  }
  .temp-card-main .temp-card-value {
    font-size: 26px;
  }
}
</style>
