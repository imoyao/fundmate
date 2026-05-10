<template>
  <div class="account-detail p-6">
    <div class="mb-6">
      <button
        class="mb-4 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center"
        @click="$router.push('/account/overview')"
      >
        <i class="fa fa-arrow-left mr-2" />返回账户概览
      </button>
      <div class="flex justify-between items-center">
        <h2 class="text-2xl font-bold">账户详情</h2>
        <div class="flex gap-2">
          <button
            class="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            编辑账户
          </button>
          <button
            class="px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors"
          >
            导出数据
          </button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <div class="bg-white rounded-xl shadow-md p-6">
        <div class="flex items-center justify-between mb-4">
          <div
            class="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center"
          >
            <i class="fa fa-wallet text-orange-500 text-xl" />
          </div>
          <span
            class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
            >+5.2%</span
          >
        </div>
        <p class="text-gray-500 text-sm mb-1">总资产</p>
        <p class="text-2xl font-bold text-gray-800">¥856,234.56</p>
      </div>

      <div class="bg-white rounded-xl shadow-md p-6">
        <div class="flex items-center justify-between mb-4">
          <div
            class="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center"
          >
            <i class="fa fa-chart-line text-green-500 text-xl" />
          </div>
          <span
            class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
            >+1.8%</span
          >
        </div>
        <p class="text-gray-500 text-sm mb-1">本月盈亏</p>
        <p class="text-2xl font-bold text-green-600">+¥23,456.78</p>
      </div>

      <div class="bg-white rounded-xl shadow-md p-6">
        <div class="flex items-center justify-between mb-4">
          <div
            class="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center"
          >
            <i class="fa fa-list text-purple-500 text-xl" />
          </div>
          <span class="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full"
            >无变化</span
          >
        </div>
        <p class="text-gray-500 text-sm mb-1">资产数量</p>
        <p class="text-2xl font-bold text-gray-800">5</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      <div class="bg-white rounded-xl shadow-md p-6">
        <h3 class="text-lg font-bold mb-4">账户资产走势</h3>
        <div class="h-64">
          <canvas ref="trendChartRef" />
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-md p-6">
        <h3 class="text-lg font-bold mb-4">资产分布</h3>
        <div class="h-64">
          <canvas ref="distributionChartRef" />
        </div>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="border-b border-gray-200">
        <nav class="flex">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            :class="[
              'px-6 py-4 text-sm font-medium transition-colors border-b-2',
              activeTab === tab.key
                ? 'border-orange-500 text-orange-500'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            ]"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </nav>
      </div>

      <div class="p-6">
        <div v-show="activeTab === 'assets'">
          <table class="w-full">
            <thead>
              <tr class="text-left text-gray-500 border-b border-gray-200">
                <th class="pb-3 font-medium">类型</th>
                <th class="pb-3 font-medium">名称</th>
                <th class="pb-3 font-medium">代码</th>
                <th class="pb-3 font-medium">市值</th>
                <th class="pb-3 font-medium">盈亏</th>
                <th class="pb-3 font-medium">盈亏率</th>
                <th class="pb-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="asset in assets"
                :key="asset.code"
                class="border-b border-gray-100 hover:bg-gray-50"
              >
                <td class="py-3">{{ asset.type }}</td>
                <td class="py-3 font-medium">{{ asset.name }}</td>
                <td class="py-3 text-gray-500">{{ asset.code }}</td>
                <td class="py-3">¥{{ asset.value.toLocaleString() }}</td>
                <td
                  :class="[
                    'py-3',
                    asset.profit >= 0 ? 'text-green-600' : 'text-red-600'
                  ]"
                >
                  {{ asset.profit >= 0 ? "+" : "" }}¥{{
                    asset.profit.toLocaleString()
                  }}
                </td>
                <td
                  :class="[
                    'py-3',
                    asset.rate >= 0 ? 'text-green-600' : 'text-red-600'
                  ]"
                >
                  {{ asset.rate >= 0 ? "+" : "" }}{{ asset.rate }}%
                </td>
                <td class="py-3">
                  <button
                    class="text-orange-500 hover:text-orange-600 text-sm mr-2"
                  >
                    编辑
                  </button>
                  <button class="text-red-500 hover:text-red-600 text-sm">
                    删除
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-show="activeTab === 'holdings'">
          <table class="w-full">
            <thead>
              <tr class="text-left text-gray-500 border-b border-gray-200">
                <th class="pb-3 font-medium">名称</th>
                <th class="pb-3 font-medium">类型</th>
                <th class="pb-3 font-medium">持有份额</th>
                <th class="pb-3 font-medium">成本价</th>
                <th class="pb-3 font-medium">当前价</th>
                <th class="pb-3 font-medium">市值</th>
                <th class="pb-3 font-medium">浮动盈亏</th>
                <th class="pb-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="holding in holdings"
                :key="holding.name"
                class="border-b border-gray-100 hover:bg-gray-50"
              >
                <td class="py-3 font-medium">{{ holding.name }}</td>
                <td class="py-3">{{ holding.type }}</td>
                <td class="py-3">{{ holding.shares.toLocaleString() }}</td>
                <td class="py-3">¥{{ holding.costPrice.toFixed(2) }}</td>
                <td class="py-3">¥{{ holding.currentPrice.toFixed(2) }}</td>
                <td class="py-3">
                  ¥{{ holding.marketValue.toLocaleString() }}
                </td>
                <td
                  :class="[
                    'py-3',
                    holding.profitLoss >= 0 ? 'text-green-600' : 'text-red-600'
                  ]"
                >
                  {{ holding.profitLoss >= 0 ? "+" : "" }}¥{{
                    holding.profitLoss.toLocaleString()
                  }}
                  ({{ holding.profitLossRate }}%)
                </td>
                <td class="py-3">
                  <button
                    class="text-orange-500 hover:text-orange-600 text-sm mr-2"
                  >
                    买入
                  </button>
                  <button class="text-red-500 hover:text-red-600 text-sm">
                    卖出
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-show="activeTab === 'transactions'">
          <table class="w-full">
            <thead>
              <tr class="text-left text-gray-500 border-b border-gray-200">
                <th class="pb-3 font-medium">日期</th>
                <th class="pb-3 font-medium">名称</th>
                <th class="pb-3 font-medium">类型</th>
                <th class="pb-3 font-medium">价格</th>
                <th class="pb-3 font-medium">数量</th>
                <th class="pb-3 font-medium">总额</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="txn in transactions"
                :key="txn.date + txn.name"
                class="border-b border-gray-100 hover:bg-gray-50"
              >
                <td class="py-3">{{ txn.date }}</td>
                <td class="py-3 font-medium">{{ txn.name }}</td>
                <td class="py-3">
                  <span
                    :class="[
                      'px-2 py-1 text-xs rounded-full',
                      txn.type === '买入'
                        ? 'bg-green-100 text-green-700'
                        : txn.type === '卖出'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-blue-100 text-blue-700'
                    ]"
                  >
                    {{ txn.type }}
                  </span>
                </td>
                <td class="py-3">¥{{ txn.price.toLocaleString() }}</td>
                <td class="py-3">{{ txn.quantity.toLocaleString() }}</td>
                <td class="py-3">¥{{ txn.total.toLocaleString() }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import * as echarts from "echarts";

const activeTab = ref("assets");
const tabs = [
  { key: "assets", label: "资产列表" },
  { key: "holdings", label: "持仓列表" },
  { key: "transactions", label: "交易记录" }
];

const assets = ref([
  {
    type: "📈",
    name: "沪深300ETF",
    code: "510300",
    value: 125678.9,
    profit: 3456.78,
    rate: 2.8
  },
  {
    type: "💰",
    name: "理财产品A",
    code: "LC20230901",
    value: 200000,
    profit: -1200,
    rate: -0.6
  },
  {
    type: "🏦",
    name: "定期存款",
    code: "DQ20230601",
    value: 300000,
    profit: 2250,
    rate: 0.75
  },
  {
    type: "🏢",
    name: "房产投资",
    code: "RE20220101",
    value: 1500000,
    profit: 15000,
    rate: 1.0
  },
  {
    type: "💎",
    name: "贵金属",
    code: "AU9999",
    value: 50000,
    profit: 1500,
    rate: 3.0
  }
]);

const holdings = ref([
  {
    name: "沪深300ETF",
    type: "股票",
    shares: 1000,
    costPrice: 4.5,
    currentPrice: 4.8,
    marketValue: 4800,
    profitLoss: 300,
    profitLossRate: 6.67
  },
  {
    name: "理财产品A",
    type: "理财",
    shares: 1,
    costPrice: 20000,
    currentPrice: 19800,
    marketValue: 19800,
    profitLoss: -200,
    profitLossRate: -1.0
  },
  {
    name: "贵金属ETF",
    type: "基金",
    shares: 500,
    costPrice: 2.1,
    currentPrice: 2.25,
    marketValue: 1125,
    profitLoss: 75,
    profitLossRate: 7.14
  }
]);

const transactions = ref([
  {
    date: "2025-07-05",
    name: "沪深300ETF",
    type: "买入",
    price: 4.5,
    quantity: 1000,
    total: 4500
  },
  {
    date: "2025-07-02",
    name: "理财产品A",
    type: "买入",
    price: 20000,
    quantity: 1,
    total: 20000
  },
  {
    date: "2025-06-28",
    name: "贵金属ETF",
    type: "卖出",
    price: 2.2,
    quantity: 200,
    total: 440
  }
]);

const trendChartRef = ref<HTMLCanvasElement | null>(null);
const distributionChartRef = ref<HTMLCanvasElement | null>(null);
let trendChart: echarts.ECharts | null = null;
let distributionChart: echarts.ECharts | null = null;

const initCharts = () => {
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value);
    trendChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { right: "4%", bottom: "3%", containLabel: true },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: ["1月", "2月", "3月", "4月", "5月", "6月", "7月"]
      },
      yAxis: { type: "value", axisLabel: { formatter: "¥{value}" } },
      series: [
        {
          name: "总资产",
          type: "line",
          smooth: true,
          data: [840000, 842000, 838000, 845000, 850000, 852000, 856234.56],
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(255, 107, 0, 0.3)" },
              { offset: 1, color: "rgba(255, 107, 0, 0.1)" }
            ])
          },
          itemStyle: { color: "#FF6B00" }
        }
      ]
    });
  }

  if (distributionChartRef.value) {
    distributionChart = echarts.init(distributionChartRef.value);
    distributionChart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { position: "bottom" },
      series: [
        {
          type: "pie",
          radius: ["40%", "70%"],
          data: [
            { value: 600000, name: "股票", itemStyle: { color: "#FF6B00" } },
            { value: 300000, name: "基金", itemStyle: { color: "#FF7D00" } },
            { value: 200000, name: "理财", itemStyle: { color: "#4CAF50" } },
            { value: 100000, name: "REITs", itemStyle: { color: "#2196F3" } },
            { value: 34567.89, name: "现金", itemStyle: { color: "#9C27B0" } }
          ]
        }
      ]
    });
  }
};

const resizeCharts = () => {
  trendChart?.resize();
  distributionChart?.resize();
};

onMounted(() => {
  nextTick(() => {
    initCharts();
    window.addEventListener("resize", resizeCharts);
  });
});
</script>

<style scoped>
.account-detail {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
