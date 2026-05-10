<template>
  <div class="bank-page p-6">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold">银行存款</h2>
        <p class="text-gray-500 mt-1">管理您的银行存款和理财产品</p>
      </div>
      <button
        class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 flex items-center shadow-sm transition-colors"
      >
        <IconifyIconOffline icon="ep:plus" class="mr-2" />
        添加存款
      </button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:wallet" class="text-green-500" />
          </div>
        </div>
        <p class="text-gray-500 text-xs">总存款</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥500,000</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:calendar" class="text-blue-500" />
          </div>
        </div>
        <p class="text-gray-500 text-xs">定期存款</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥300,000</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:odometer" class="text-purple-500" />
          </div>
        </div>
        <p class="text-gray-500 text-xs">活期存款</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥200,000</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:circle-check" class="text-green-500" />
          </div>
          <span class="text-green-500 text-xs">低风险</span>
        </div>
        <p class="text-gray-500 text-xs">风险等级</p>
        <p class="text-xl font-bold text-green-600 mt-1">低风险</p>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">存款名称</th>
              <th class="px-4 py-3 text-left font-medium">类型</th>
              <th class="px-4 py-3 text-right font-medium">金额</th>
              <th class="px-4 py-3 text-right font-medium">年利率</th>
              <th class="px-4 py-3 text-left font-medium">存入日期</th>
              <th class="px-4 py-3 text-left font-medium">到期日期</th>
              <th class="px-4 py-3 text-center font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">定期存款A</td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded"
                  >定期</span
                >
              </td>
              <td class="px-4 py-3 text-right">¥200,000</td>
              <td class="px-4 py-3 text-right text-green-600">2.75%</td>
              <td class="px-4 py-3">2024-01-15</td>
              <td class="px-4 py-3">2025-01-15</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200"
                >
                  详情
                </button>
              </td>
            </tr>
            <tr class="border-t bg-gray-50/50 hover:bg-gray-100">
              <td class="px-4 py-3 font-medium">定期存款B</td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded"
                  >定期</span
                >
              </td>
              <td class="px-4 py-3 text-right">¥100,000</td>
              <td class="px-4 py-3 text-right text-green-600">3.25%</td>
              <td class="px-4 py-3">2024-03-01</td>
              <td class="px-4 py-3">2027-03-01</td>
              <td class="px-4 py-3 text-center">
                <button
                  class="px-3 py-1 bg-gray-100 text-gray-600 text-xs rounded-lg hover:bg-gray-200"
                >
                  详情
                </button>
              </td>
            </tr>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">活期储蓄</td>
              <td class="px-4 py-3">
                <span
                  class="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded"
                  >活期</span
                >
              </td>
              <td class="px-4 py-3 text-right">¥200,000</td>
              <td class="px-4 py-3 text-right text-green-600">0.35%</td>
              <td class="px-4 py-3">-</td>
              <td class="px-4 py-3">-</td>
              <td class="px-4 py-3 text-center">
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
.bank-page {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
