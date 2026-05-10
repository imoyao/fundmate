<template>
  <div class="precious-page p-6">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold">贵金属</h2>
        <p class="text-gray-500 mt-1">管理您的贵金属投资</p>
      </div>
      <button
        class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 flex items-center shadow-sm transition-colors"
      >
        <IconifyIconOffline icon="ep:plus" class="mr-2" />
        添加贵金属
      </button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:medal" class="text-yellow-500" />
          </div>
          <span class="text-green-500 text-xs">+2.1%</span>
        </div>
        <p class="text-gray-500 text-xs">总市值</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥58,000</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:coin" class="text-green-500" />
          </div>
          <span class="text-green-500 text-xs">+¥6,000</span>
        </div>
        <p class="text-gray-500 text-xs">浮动盈亏</p>
        <p class="text-xl font-bold text-green-600 mt-1">+¥6,000</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:scale" class="text-yellow-600" />
          </div>
          <span class="text-gray-500 text-xs">100克</span>
        </div>
        <p class="text-gray-500 text-xs">持有总量</p>
        <p class="text-xl font-bold text-gray-800 mt-1">100 克</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:set-up" class="text-amber-500" />
          </div>
          <span class="text-amber-500 text-xs">中等</span>
        </div>
        <p class="text-gray-500 text-xs">风险等级</p>
        <p class="text-xl font-bold text-amber-600 mt-1">中风险</p>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">品种</th>
              <th class="px-4 py-3 text-left font-medium">类型</th>
              <th class="px-4 py-3 text-right font-medium">持有重量</th>
              <th class="px-4 py-3 text-right font-medium">买入价格</th>
              <th class="px-4 py-3 text-right font-medium">当前价格</th>
              <th class="px-4 py-3 text-right font-medium">市值</th>
              <th class="px-4 py-3 text-right font-medium">浮动盈亏</th>
              <th class="px-4 py-3 text-center font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">实物黄金</td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-xs rounded"
                  >Au99.99</span
                >
              </td>
              <td class="px-4 py-3 text-right">100 克</td>
              <td class="px-4 py-3 text-right">¥520/克</td>
              <td class="px-4 py-3 text-right text-yellow-600">¥580/克</td>
              <td class="px-4 py-3 text-right">¥58,000</td>
              <td class="px-4 py-3 text-right text-green-600">+¥6,000</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 mr-1"
                >
                  买入
                </button>
                <button
                  class="px-3 py-1 bg-red-500 text-white text-xs rounded-lg hover:bg-red-600"
                >
                  卖出
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
.precious-page {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
