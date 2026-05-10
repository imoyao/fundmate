<template>
  <div class="funds-page p-6">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold">基金资产</h2>
        <p class="text-gray-500 mt-1">管理您的基金投资组合</p>
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
          申购基金
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:box" class="text-amber-500" />
          </div>
          <span class="text-red-500 text-xs flex items-center"
            ><IconifyIconOffline
              icon="ep:arrow-down-bold"
              class="mr-0.5"
            />-1.2%</span
          >
        </div>
        <p class="text-gray-500 text-xs">总市值</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥678,950</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:coin" class="text-green-500" />
          </div>
          <span class="text-red-500 text-xs flex items-center"
            ><IconifyIconOffline
              icon="ep:arrow-down-bold"
              class="mr-0.5"
            />-¥1,750</span
          >
        </div>
        <p class="text-gray-500 text-xs">持仓盈亏</p>
        <p class="text-xl font-bold text-red-600 mt-1">-¥8,520</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:collection" class="text-blue-500" />
          </div>
          <span class="text-gray-500 text-xs">5只</span>
        </div>
        <p class="text-gray-500 text-xs">持仓数量</p>
        <p class="text-xl font-bold text-gray-800 mt-1">5 只</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:money" class="text-yellow-600" />
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
            placeholder="搜索基金名称/代码..."
            class="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-orange-500 shadow-sm flex-1 max-w-xs"
          />
          <select
            class="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:border-orange-500 shadow-sm"
          >
            <option>全部类型</option>
            <option>股票型</option>
            <option>混合型</option>
            <option>债券型</option>
            <option>指数型</option>
          </select>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">基金名称</th>
              <th class="px-4 py-3 text-left font-medium">代码</th>
              <th class="px-4 py-3 text-right font-medium">持有份额</th>
              <th class="px-4 py-3 text-right font-medium">单位净值</th>
              <th class="px-4 py-3 text-right font-medium">持仓成本</th>
              <th class="px-4 py-3 text-right font-medium">市值</th>
              <th class="px-4 py-3 text-right font-medium">浮动盈亏</th>
              <th class="px-4 py-3 text-center font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">易方达消费精选</td>
              <td class="px-4 py-3 text-gray-500">009265</td>
              <td class="px-4 py-3 text-right">50,000 份</td>
              <td class="px-4 py-3 text-right text-red-600">¥1.245</td>
              <td class="px-4 py-3 text-right">¥1.280</td>
              <td class="px-4 py-3 text-right">¥62,250</td>
              <td class="px-4 py-3 text-right text-red-600">-¥1,750</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 mr-1"
                >
                  申购
                </button>
                <button
                  class="px-3 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600"
                >
                  赎回
                </button>
              </td>
            </tr>
            <tr class="border-t bg-gray-50/50 hover:bg-gray-100">
              <td class="px-4 py-3 font-medium">纳斯达克100ETF</td>
              <td class="px-4 py-3 text-gray-500">513100</td>
              <td class="px-4 py-3 text-right">10,000 份</td>
              <td class="px-4 py-3 text-right text-green-600">¥1.978</td>
              <td class="px-4 py-3 text-right">¥1.850</td>
              <td class="px-4 py-3 text-right">¥19,780</td>
              <td class="px-4 py-3 text-right text-green-600">+¥1,280</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 mr-1"
                >
                  申购
                </button>
                <button
                  class="px-3 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600"
                >
                  赎回
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
.funds-page {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
