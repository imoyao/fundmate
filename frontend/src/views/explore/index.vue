<template>
  <div class="explore-page">
    <!-- 顶部导航 -->
    <header class="explore-header">
      <div class="header-inner">
        <div class="logo-area">
          <span class="logo">ShowBuy</span>
          <span class="badge">探市 · 研究</span>
        </div>
        <div class="nav-actions">
          <el-button link @click="showWhyModal">为什么选 ShowBuy</el-button>
          <el-button type="primary" @click="goToRegister">立即注册 →</el-button>
        </div>
      </div>
    </header>

    <!-- HERO 区 -->
    <section class="hero-section">
      <h1>发现机会，研究标的，做出更好的投资决策</h1>
      <p>添加你关注的资产，实时追踪估值，探索市场机会</p>
      <div class="hero-actions">
        <el-button type="primary" size="large" @click="scrollToAdd">
          开始体验 ↓
        </el-button>
        <el-button plain size="large" @click="loadDemoData">
          查看演示
        </el-button>
      </div>
    </section>

    <!-- 市场概览区 -->
    <section class="market-overview">
      <div class="overview-inner">
        <!-- 指数卡片 -->
        <div class="index-cards">
          <div v-for="idx in indexData" :key="idx.code" class="index-card">
            <div class="index-header">
              <span class="index-name">{{ idx.name }}</span>
              <span class="index-code">{{ idx.code }}</span>
            </div>
            <div class="index-price">{{ idx.price }}</div>
            <div class="index-change">
              <RiseFallText :value="idx.changePercent" />
              <span class="index-change-abs">{{ idx.changeAbs }}</span>
            </div>
          </div>
        </div>

        <!-- 市场温度计 -->
        <div class="temperature-card">
          <div class="temp-header">
            <span class="temp-title">市场温度计</span>
            <span class="temp-badge" :class="tempLevelClass">
              {{ tempLevelText }}
            </span>
          </div>
          <div class="temp-body">
            <div class="temp-value">
              <span class="temp-number">{{ tempPE }}</span>
              <span class="temp-unit">PE</span>
            </div>
            <div class="temp-bar">
              <div class="temp-track">
                <div class="temp-fill" :style="{ width: tempPercent + '%' }" />
              </div>
              <div class="temp-labels">
                <span>低估</span>
                <span>正常</span>
                <span>高估</span>
              </div>
            </div>
            <div class="temp-desc">{{ tempDescription }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================================ -->
    <!-- 添加/观察栏 -->
    <!-- ============================================ -->
    <section id="add-section" class="add-section">
      <div class="add-card">
        <div class="add-form-row">
          <!-- 搜索输入框 + 远程联想 -->
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
                  <el-tag size="small" class="suggestion-tag">
                    {{ getTypeLabel(item.type) }}
                  </el-tag>
                </div>
              </template>
            </el-autocomplete>
          </div>

          <!-- 类型下拉 -->
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

          <!-- 成本价（选填） -->
          <el-input
            v-model="newAsset.costPriceInput"
            placeholder="成本价（选填）"
            size="large"
            class="price-input"
            clearable
          >
            <template #prepend>¥</template>
          </el-input>

          <!-- 份额（选填） -->
          <el-input
            v-model="newAsset.quantityInput"
            placeholder="份额（选填）"
            size="large"
            class="qty-input"
            clearable
          />

          <!-- 添加按钮 -->
          <el-button
            type="primary"
            size="large"
            :loading="adding"
            @click="handleAdd"
          >
            添加观察
          </el-button>
        </div>

        <!-- 热门预置卡片 -->
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

    <!-- ============================================ -->
    <!-- 观察列表 -->
    <!-- ============================================ -->
    <section class="watchlist-section">
      <!-- 摘要行 -->
      <div class="summary-bar">
        <div class="summary-left">
          <span class="summary-count">共 {{ totalCount }} 项</span>
          <template v-if="!isPureObservationMode && summary">
            <span class="summary-divider">|</span>
            <span class="summary-value">
              总市值
              <MoneyDisplay
                :value="summary.totalMarketValue"
                :show-sign="false"
              />
            </span>
            <span class="summary-divider">|</span>
            <span class="summary-pnl">
              盈亏 <RiseFallText :value="summary.totalPnl" suffix="" />
            </span>
          </template>
          <span v-if="isPureObservationMode" class="summary-hint">
            输入成本与份额后可查看持仓盈亏
          </span>
        </div>
        <div class="summary-right">
          <span class="status-indicator">
            <span class="status-dot" :class="statusClass" />
            {{ statusText }}
          </span>
          <span v-if="lastUpdateTime" class="update-time">
            更新: {{ lastUpdateTime }}
          </span>
          <el-button size="small" @click="manualRefresh">刷新</el-button>
        </div>
      </div>

      <!-- 表格 -->
      <el-table
        :data="tableData"
        border
        style="width: 100%"
        v-loading="loading"
        empty-text="暂无观察资产，添加你关注的标的开始研究"
      >
        <!-- 产品信息 -->
        <el-table-column label="产品" min-width="180">
          <template #default="{ row }">
            <ProductDisplay
              :name="row.name"
              :symbol="row.symbol"
              :type-label="getTypeLabel(row.type)"
            />
          </template>
        </el-table-column>

        <!-- 最新价（直接使用 row.price） -->
        <el-table-column label="最新价" width="120" align="right">
          <template #default="{ row }">
            <MoneyDisplay :value="row.price" :show-sign="false" />
          </template>
        </el-table-column>

        <!-- 涨跌幅（直接使用 row.changePct） -->
        <el-table-column label="涨跌幅" width="110" align="right">
          <template #default="{ row }">
            <RiseFallText :value="row.changePct" />
          </template>
        </el-table-column>

        <!-- 当日盈亏（仅当有成本/份额时显示） -->
        <el-table-column
          v-if="!isPureObservationMode"
          label="当日盈亏"
          width="130"
          align="right"
        >
          <template #default="{ row }">
            <MoneyDisplay :value="row.pnl ?? 0" :show-sign="true" />
          </template>
        </el-table-column>

        <!-- 持仓收益（仅当有成本/份额时显示） -->
        <el-table-column
          v-if="!isPureObservationMode"
          label="持仓收益"
          width="130"
          align="right"
        >
          <template #default="{ row }">
            <MoneyDisplay :value="row.positionPnl ?? 0" :show-sign="true" />
          </template>
        </el-table-column>

        <!-- 深度分析 -->
        <el-table-column label="深度分析" width="120" align="center">
          <template #default="{ row }">
            <el-dropdown @command="handleJump(row, $event)">
              <el-button size="small" type="primary" plain> 分析 ▼ </el-button>
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

        <!-- 操作 -->
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              type="text"
              size="small"
              style="color: var(--text-tertiary)"
              @click="handleRemove(row.id)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 底部转化区 -->
    <footer class="conversion-section">
      <div class="conversion-card">
        <div class="conversion-content">
          <div class="conversion-icon">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"
                stroke="var(--brand-700)"
                stroke-width="1.5"
              />
              <path
                d="M8 12h8M12 8v8"
                stroke="var(--brand-700)"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M12 22v-4M12 6V2"
                stroke="var(--brand-700)"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <circle cx="12" cy="12" r="2" fill="var(--brand-700)" />
            </svg>
          </div>
          <h3>您的数据仅保存在本地</h3>
          <p>注册后自动同步至云端，更换设备也不丢失</p>
          <div v-if="totalCount >= 3" class="loss-aversion">
            已添加 {{ totalCount }} 项资产，清除浏览器缓存将丢失数据
          </div>
          <el-button type="primary" size="large" @click="goToRegister">
            立即注册，永久免费 →
          </el-button>
          <span class="migrate-hint"
            >注册后当前数据将自动迁移，无需重新录入</span
          >
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useLocalHoldings } from "@/composables/useLocalHoldings";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { useAssetSearch } from "@/composables/useAssetSearch";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { batchFetchQuotes } from "@/utils/realtimeDataSources";

defineOptions({
  name: "ExplorePage"
});

const router = useRouter();

// ============================================
// 本地持仓（安全初始化）
// ============================================
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

// ============================================
// 实时估值（使用 useRealtimeQuotes 组合式函数）
// ============================================
const {
  items, // 行情数据数组
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

// 构建 symbol -> 行情数据的映射（用于快速查找）
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

// 监听 holdings 变化，触发估值刷新
watch(
  () => holdings.value,
  newHoldings => {
    if (enabled.value && newHoldings && newHoldings.length > 0) {
      manualRefresh();
    }
  },
  { deep: true }
);

// ============================================
// 市场概览：指数数据
// ============================================
interface IndexInfo {
  code: string;
  name: string;
  price: string;
  changePercent: number;
  changeAbs: string;
}

const indexCodes = [
  { symbol: "000300", type: "stock" as const },
  { symbol: "000905", type: "stock" as const },
  { symbol: "399006", type: "stock" as const }
];

const indexData = ref<IndexInfo[]>([
  {
    code: "000300",
    name: "沪深300",
    price: "--",
    changePercent: 0,
    changeAbs: "--"
  },
  {
    code: "000905",
    name: "中证500",
    price: "--",
    changePercent: 0,
    changeAbs: "--"
  },
  {
    code: "399006",
    name: "创业板指",
    price: "--",
    changePercent: 0,
    changeAbs: "--"
  }
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
          changePercent: change,
          changeAbs:
            change !== 0
              ? change > 0
                ? `+${change.toFixed(2)}`
                : change.toFixed(2)
              : "--"
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

// ============================================
// 市场温度计（静态）
// ============================================
const tempPE = ref(12.3);
const tempPercent = ref(45);
const tempLevel = ref<"低估" | "正常" | "高估">("正常");

const tempLevelClass = computed(() => {
  switch (tempLevel.value) {
    case "低估":
      return "temp-low";
    case "高估":
      return "temp-high";
    default:
      return "temp-normal";
  }
});

const tempLevelText = computed(() => tempLevel.value);

const tempDescription = computed(() => {
  switch (tempLevel.value) {
    case "低估":
      return "当前市场估值处于历史较低水平，配置性价比较高";
    case "高估":
      return "当前市场估值处于历史较高水平，需注意风险";
    default:
      return "当前市场估值处于历史中间区间，建议均衡配置";
  }
});

const fetchTemperature = async () => {
  tempPE.value = 12.3;
  tempPercent.value = 45;
  tempLevel.value = "正常";
};

// ============================================
// 搜索（复用 useAssetSearch）
// ============================================
const { loading: searchLoading, results: searchResults, search } = useAssetSearch();

const querySearch = (queryString: string, cb: (results: any[]) => void) => {
  search(queryString, cb);
};

// ============================================
// 新资产表单
// ============================================
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

  // 优先从选中的资产信息获取名称
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

// ============================================
// 热门预置
// ============================================
const hotAssets = [
  {
    symbol: "510300",
    name: "沪深300ETF",
    type: "etf" as const,
    costPrice: 4.567,
    quantity: 100
  },
  {
    symbol: "513100",
    name: "纳指ETF",
    type: "etf" as const,
    costPrice: 1.234,
    quantity: 100
  },
  {
    symbol: "600036",
    name: "招商银行",
    type: "stock" as const,
    costPrice: 34.56,
    quantity: 100
  },
  {
    symbol: "588000",
    name: "科创50ETF",
    type: "etf" as const,
    costPrice: 0.987,
    quantity: 100
  }
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

// ============================================
// 表格数据（使用 quotesMap 安全访问，统一字段）
// ============================================
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
      const price = quote?.currentPrice ?? 0;      // 统一使用 currentPrice
      const changePct = quote?.changePct ?? 0;     // 统一使用 changePct
      const cost = h.costPrice ?? 0;
      const qty = h.quantity ?? 0;
      const prevClose = quote?.prevClose ?? price;
      const pnl = (price - prevClose) * qty;
      const positionPnl = (price - cost) * qty;
      return {
        ...h,
        quote,
        price,           // 显式传递，模板直接使用
        changePct,       // 显式传递
        pnl,
        positionPnl
      };
    });
  } catch {
    return [];
  }
});

// ============================================
// 删除
// ============================================
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

// ============================================
// 深度分析跳转
// ============================================
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

// ============================================
// 状态指示器
// ============================================
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

// ============================================
// 工具方法
// ============================================
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

// ============================================
// 页面方法
// ============================================
const scrollToAdd = () => {
  document
    .getElementById("add-section")
    ?.scrollIntoView({ behavior: "smooth" });
};

const loadDemoData = () => {
  hotAssets.forEach(item => {
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

// ============================================
// 生命周期
// ============================================
onMounted(() => {
  if (!enabled.value) {
    toggle(true);
  }
  fetchIndexData();
  fetchTemperature();
});
</script>

<style lang="scss" scoped>
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

/* ===== HERO ===== */
.hero-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 60px 24px 40px;
  text-align: center;

  h1 {
    font-size: 32px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 12px;
  }

  p {
    font-size: 16px;
    color: var(--text-secondary);
    margin-bottom: 24px;
  }

  .hero-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
  }
}

/* 市场概览区样式 */
.market-overview {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px 24px;

  .overview-inner {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: 20px;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
    }
  }
}

/* 指数卡片 */
.index-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.index-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px 24px;
  box-shadow: var(--shadow-raised);
  border: 1px solid var(--border-light);

  .index-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .index-name {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .index-code {
    font-size: 11px;
    color: var(--text-tertiary);
  }

  .index-price {
    font-size: 24px;
    font-weight: 600;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    margin-bottom: 4px;
  }

  .index-change {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }

  .index-change-abs {
    color: var(--text-tertiary);
    font-size: 13px;
  }
}

/* 温度计卡片 */
.temperature-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px 24px;
  box-shadow: var(--shadow-raised);
  border: 1px solid var(--border-light);

  .temp-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .temp-title {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .temp-badge {
    font-size: 12px;
    padding: 2px 12px;
    border-radius: 12px;

    &.temp-low {
      background: var(--color-fall);
      color: white;
    }
    &.temp-normal {
      background: var(--tag-warm-sand);
      color: var(--text-primary);
    }
    &.temp-high {
      background: var(--color-rise);
      color: white;
    }
  }

  .temp-body {
    .temp-value {
      display: flex;
      align-items: baseline;
      gap: 4px;
      margin-bottom: 12px;
    }

    .temp-number {
      font-size: 28px;
      font-weight: 600;
      color: var(--text-primary);
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }

    .temp-unit {
      font-size: 14px;
      color: var(--text-tertiary);
    }

    .temp-bar {
      margin-bottom: 8px;

      .temp-track {
        height: 6px;
        border-radius: 3px;
        background: var(--bg-soft);
        position: relative;
        overflow: hidden;
      }

      .temp-fill {
        height: 100%;
        border-radius: 3px;
        background: linear-gradient(
          to right,
          var(--color-fall),
          var(--tag-warm-sand),
          var(--color-rise)
        );
        transition: width 0.6s ease;
      }

      .temp-labels {
        display: flex;
        justify-content: space-between;
        font-size: 11px;
        color: var(--text-tertiary);
        margin-top: 4px;
      }
    }

    .temp-desc {
      font-size: 13px;
      color: var(--text-secondary);
      margin-top: 8px;
    }
  }
}

/* ===== 添加/观察栏 ===== */
.add-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px 24px;
}

.add-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 24px;
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
  margin-top: 16px;
  padding-top: 16px;
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
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

/* ===== 底部转化区 ===== */
.conversion-section {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px 48px;
}

.conversion-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 48px 32px;
  text-align: center;
  box-shadow: var(--shadow-raised);
  border: 1px solid var(--border-light);
}

.conversion-content {
  max-width: 480px;
  margin: 0 auto;

  .conversion-icon {
    margin-bottom: 12px;
  }

  h3 {
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 8px;
  }

  p {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 16px;
  }

  .loss-aversion {
    padding: 12px 16px;
    border-radius: 8px;
    background: var(--brand-100);
    color: var(--brand-700);
    font-size: 14px;
    margin-bottom: 20px;
  }

  .migrate-hint {
    display: block;
    margin-top: 12px;
    font-size: 13px;
    color: var(--text-tertiary);
  }
}

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .add-form-row {
    flex-direction: column;

    .input-wrapper,
    .type-select,
    .price-input,
    .qty-input {
      width: 100%;
      flex-shrink: 1;
    }

    .type-select {
      width: 100%;
    }
  }

  .hot-section {
    flex-direction: column;
    align-items: flex-start;

    .hot-cards {
      width: 100%;
    }
  }

  .summary-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .hero-section h1 {
    font-size: 24px;
  }

  .conversion-card {
    padding: 32px 20px;
  }
}
</style>
