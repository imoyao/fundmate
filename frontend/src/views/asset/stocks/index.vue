<template>
  <div class="stocks-page p-6">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold">股票资产</h2>
        <p class="text-gray-500 mt-1">管理您的股票投资组合</p>
      </div>
      <div class="flex gap-3">
        <button
          class="px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm hover:bg-gray-50 flex items-center shadow-sm transition-colors"
        >
          <IconifyIconOffline icon="ep:download" class="mr-2 text-gray-500" />
          导出
        </button>
        <button
          class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 flex items-center shadow-sm transition-colors"
        >
          <IconifyIconOffline icon="ep:plus" class="mr-2" />
          添加股票
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:trend-charts" class="text-red-500" />
          </div>
          <span class="text-green-500 text-xs flex items-center"
            ><IconifyIconOffline
              icon="ep:arrow-up-bold"
              class="mr-0.5"
            />+2.5%</span
          >
        </div>
        <p class="text-gray-500 text-xs">总市值</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥856,240</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:coin" class="text-green-500" />
          </div>
          <span class="text-green-500 text-xs flex items-center"
            ><IconifyIconOffline
              icon="ep:arrow-up-bold"
              class="mr-0.5"
            />+¥12,800</span
          >
        </div>
        <p class="text-gray-500 text-xs">持仓盈亏</p>
        <p class="text-xl font-bold text-green-600 mt-1">+¥45,680</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:collection" class="text-blue-500" />
          </div>
          <span class="text-gray-500 text-xs">3只</span>
        </div>
        <p class="text-gray-500 text-xs">持仓数量</p>
        <p class="text-xl font-bold text-gray-800 mt-1">3 只</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:卖掉" class="text-orange-500" />
          </div>
          <span class="text-amber-500 text-xs">中等</span>
        </div>
        <p class="text-gray-500 text-xs">风险等级</p>
        <p class="text-xl font-bold text-amber-600 mt-1">中风险</p>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="p-4 border-b border-gray-100">
        <div class="flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="搜索股票名称/代码..."
            class="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-orange-500 shadow-sm flex-1 max-w-xs"
          />
          <select
            class="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-orange-500 shadow-sm"
          >
            <option>全部账户</option>
            <option>股票账户A</option>
            <option>股票账户B</option>
          </select>
          <select
            class="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-orange-500 shadow-sm"
          >
            <option>全部状态</option>
            <option>持仓中</option>
            <option>已清仓</option>
          </select>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">股票名称</th>
              <th class="px-4 py-3 text-left font-medium">代码</th>
              <th class="px-4 py-3 text-right font-medium">持仓数量</th>
              <th class="px-4 py-3 text-right font-medium">成本价</th>
              <th class="px-4 py-3 text-right font-medium">当前价</th>
              <th class="px-4 py-3 text-right font-medium">市值</th>
              <th class="px-4 py-3 text-right font-medium">盈亏</th>
              <th class="px-4 py-3 text-right font-medium">盈亏率</th>
              <th class="px-4 py-3 text-center font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">腾讯控股</td>
              <td class="px-4 py-3 text-gray-500">00700.HK</td>
              <td class="px-4 py-3 text-right">500 股</td>
              <td class="px-4 py-3 text-right">¥320.00</td>
              <td class="px-4 py-3 text-right text-orange-500">¥345.60</td>
              <td class="px-4 py-3 text-right">¥172,800</td>
              <td class="px-4 py-3 text-right text-green-600">+¥12,800</td>
              <td class="px-4 py-3 text-right text-green-600">+8.00%</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 mr-1"
                >
                  交易
                </button>
                <button
                  class="px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200"
                >
                  详情
                </button>
              </td>
            </tr>
            <tr class="border-t bg-gray-50/50 hover:bg-gray-100">
              <td class="px-4 py-3 font-medium">贵州茅台</td>
              <td class="px-4 py-3 text-gray-500">600519.SH</td>
              <td class="px-4 py-3 text-right">100 股</td>
              <td class="px-4 py-3 text-right">¥1,450.00</td>
              <td class="px-4 py-3 text-right text-orange-500">¥1,520.00</td>
              <td class="px-4 py-3 text-right">¥152,000</td>
              <td class="px-4 py-3 text-right text-green-600">+¥7,000</td>
              <td class="px-4 py-3 text-right text-green-600">+4.83%</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 mr-1"
                >
                  交易
                </button>
                <button
                  class="px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200"
                >
                  详情
                </button>
              </td>
            </tr>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">苹果公司</td>
              <td class="px-4 py-3 text-gray-500">AAPL.US</td>
              <td class="px-4 py-3 text-right">50 股</td>
              <td class="px-4 py-3 text-right">¥1,200.00</td>
              <td class="px-4 py-3 text-right text-orange-500">¥1,350.00</td>
              <td class="px-4 py-3 text-right">¥67,500</td>
              <td class="px-4 py-3 text-right text-green-600">+¥7,500</td>
              <td class="px-4 py-3 text-right text-green-600">+12.50%</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 mr-1"
                >
                  交易
                </button>
                <button
                  class="px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200"
                >
                  详情
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
</script>

<style scoped>
.stocks-page {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
