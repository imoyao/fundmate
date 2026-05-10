<template>
  <div class="account-management p-6">
    <div class="mb-8">
      <h2 class="text-[clamp(1.5rem,3vw,2.5rem)] font-bold">账户管理</h2>
      <p class="text-gray-500 mt-1">管理您的账户信息</p>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="p-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div class="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <h3 class="text-lg font-bold mb-4">账户信息</h3>
            <div class="space-y-4">
              <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-500">账户持有人</span>
                <span class="font-medium">张小明</span>
              </div>
              <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-500">账户类型</span>
                <span class="font-medium">综合理财账户</span>
              </div>
              <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-500">开户日期</span>
                <span class="font-medium">2024-01-15</span>
              </div>
              <div class="flex justify-between py-2">
                <span class="text-gray-500">最近登录</span>
                <span class="font-medium">2025-07-09 08:45</span>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <h3 class="text-lg font-bold mb-4">资金状况</h3>
            <div class="space-y-4">
              <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-500">可用资金</span>
                <span class="font-medium text-orange-500">¥125,680.00</span>
              </div>
              <div class="flex justify-between py-2 border-b border-gray-100">
                <span class="text-gray-500">总资产</span>
                <span class="font-medium text-orange-500">¥2,345,678.00</span>
              </div>
              <div class="flex justify-between py-2">
                <span class="text-gray-500">累计收益</span>
                <span class="font-medium text-green-600">+¥245,678.00</span>
              </div>
            </div>
          </div>
        </div>

        <div class="mb-8">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-bold">最近交易记录</h3>
            <a
              href="#"
              class="text-orange-500 hover:text-orange-600 text-sm font-medium"
              >查看全部</a
            >
          </div>
          <div class="bg-white rounded-lg shadow-sm border border-gray-200">
            <div class="overflow-x-auto">
              <table class="w-full">
                <thead>
                  <tr class="text-left text-gray-500 bg-gray-50">
                    <th class="pb-3 pt-3 pl-4 font-medium">交易日期</th>
                    <th class="pb-3 pt-3 font-medium">资产名称</th>
                    <th class="pb-3 pt-3 font-medium">交易类型</th>
                    <th class="pb-3 pt-3 font-medium">金额</th>
                    <th class="pb-3 pt-3 pr-4 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="border-t border-gray-100 hover:bg-gray-50">
                    <td class="py-3 pl-4">2025-07-05</td>
                    <td class="py-3">腾讯控股</td>
                    <td class="py-3">
                      <span
                        class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
                        >买入</span
                      >
                    </td>
                    <td class="py-3">¥34,560.00</td>
                    <td class="py-3 pr-4">
                      <span
                        class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
                        >已完成</span
                      >
                    </td>
                  </tr>
                  <tr
                    class="border-t border-gray-100 hover:bg-gray-50 bg-gray-50/50"
                  >
                    <td class="py-3 pl-4">2025-07-02</td>
                    <td class="py-3">易方达消费精选</td>
                    <td class="py-3">
                      <span
                        class="px-2 py-1 bg-red-100 text-red-700 text-xs rounded-full"
                        >赎回</span
                      >
                    </td>
                    <td class="py-3">¥6,250.00</td>
                    <td class="py-3 pr-4">
                      <span
                        class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
                        >已完成</span
                      >
                    </td>
                  </tr>
                  <tr class="border-t border-gray-100 hover:bg-gray-50">
                    <td class="py-3 pl-4">2025-06-28</td>
                    <td class="py-3">贵州茅台</td>
                    <td class="py-3">
                      <span
                        class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
                        >买入</span
                      >
                    </td>
                    <td class="py-3">¥152,000.00</td>
                    <td class="py-3 pr-4">
                      <span
                        class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
                        >已完成</span
                      >
                    </td>
                  </tr>
                  <tr
                    class="border-t border-gray-100 hover:bg-gray-50 bg-gray-50/50"
                  >
                    <td class="py-3 pl-4">2025-06-25</td>
                    <td class="py-3">纳斯达克100ETF</td>
                    <td class="py-3">
                      <span
                        class="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded-full"
                        >分红</span
                      >
                    </td>
                    <td class="py-3">¥1,280.00</td>
                    <td class="py-3 pr-4">
                      <span
                        class="px-2 py-1 bg-green-100 text-green-700 text-xs rounded-full"
                        >已完成</span
                      >
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div>
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-bold">我的账户</h3>
            <button
              class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 transition-colors"
            >
              + 新增账户
            </button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div
              class="border border-gray-200 rounded-lg p-5 hover:shadow-lg transition-shadow cursor-pointer"
            >
              <div class="flex items-center mb-4">
                <div
                  class="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center mr-3"
                >
                  <span class="text-2xl">💳</span>
                </div>
                <div>
                  <h4 class="font-bold">家庭共同账户</h4>
                  <p class="text-sm text-gray-500">3个成员</p>
                </div>
              </div>
              <div class="space-y-2 mb-4">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500">总资产</span>
                  <span class="font-medium text-green-600">¥856,234.56</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500">日盈亏</span>
                  <span class="font-medium text-green-600">+¥1,234.56</span>
                </div>
              </div>
              <button
                class="w-full py-2 bg-orange-50 text-orange-500 rounded-lg text-sm hover:bg-orange-100 transition-colors"
              >
                查看详情
              </button>
            </div>

            <div
              class="border border-gray-200 rounded-lg p-5 hover:shadow-lg transition-shadow cursor-pointer"
            >
              <div class="flex items-center mb-4">
                <div
                  class="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mr-3"
                >
                  <span class="text-2xl">💼</span>
                </div>
                <div>
                  <h4 class="font-bold">个人账户A</h4>
                  <p class="text-sm text-gray-500">1个成员</p>
                </div>
              </div>
              <div class="space-y-2 mb-4">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500">总资产</span>
                  <span class="font-medium text-red-600">¥378,333.33</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-500">日盈亏</span>
                  <span class="font-medium text-red-600">-¥567.89</span>
                </div>
              </div>
              <button
                class="w-full py-2 bg-orange-50 text-orange-500 rounded-lg text-sm hover:bg-orange-100 transition-colors"
              >
                查看详情
              </button>
            </div>

            <div
              class="border border-gray-200 border-dashed rounded-lg p-5 hover:shadow-lg transition-shadow cursor-pointer flex flex-col items-center justify-center text-gray-400 hover:text-orange-500"
            >
              <div
                class="w-12 h-12 border-2 border-dashed border-gray-300 rounded-full flex items-center justify-center mb-3"
              >
                <span class="text-2xl">+</span>
              </div>
              <span class="text-sm">添加新账户</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
</script>

<style scoped>
.account-management {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
