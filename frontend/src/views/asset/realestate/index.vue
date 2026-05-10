<template>
  <div class="realestate-page p-6">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold">房产资产</h2>
        <p class="text-gray-500 mt-1">管理您的房产投资</p>
      </div>
      <button
        class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 flex items-center shadow-sm transition-colors"
      >
        <IconifyIconOffline icon="ep:plus" class="mr-2" />
        添加房产
      </button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:house" class="text-green-500" />
          </div>
          <span class="text-green-500 text-xs">+3.7%</span>
        </div>
        <p class="text-gray-500 text-xs">总估值</p>
        <p class="text-xl font-bold text-gray-800 mt-1">¥810,488</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline
              icon="ep:office-building"
              class="text-blue-500"
            />
          </div>
          <span class="text-green-500 text-xs">+¥130,488</span>
        </div>
        <p class="text-gray-500 text-xs">累计增值</p>
        <p class="text-xl font-bold text-green-600 mt-1">+¥130,488</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline icon="ep:document" class="text-purple-500" />
          </div>
          <span class="text-gray-500 text-xs">1套</span>
        </div>
        <p class="text-gray-500 text-xs">房产数量</p>
        <p class="text-xl font-bold text-gray-800 mt-1">1 套</p>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex items-center justify-between mb-2">
          <div
            class="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"
          >
            <IconifyIconOffline
              icon="icon-park:low-price"
              class="text-green-500"
            />
          </div>
          <span class="text-green-500 text-xs">低风险</span>
        </div>
        <p class="text-gray-500 text-xs">风险等级</p>
        <p class="text-xl font-bold text-green-600 mt-1">低风险</p>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="bg-white rounded-xl shadow-md overflow-hidden">
        <div
          class="h-48 bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center"
        >
          <IconifyIconOffline
            icon="ep:picture"
            class="text-blue-400 text-6xl"
          />
        </div>
        <div class="p-5">
          <div class="flex justify-between items-start mb-3">
            <div>
              <h3 class="font-bold text-lg">阳光花园小区</h3>
              <p class="text-gray-500 text-sm">广东省深圳市南山区</p>
            </div>
            <span
              class="px-2 py-0.5 bg-green-100 text-green-600 text-xs rounded-full"
              >自住</span
            >
          </div>
          <div class="grid grid-cols-2 gap-4 mb-4 text-sm">
            <div>
              <p class="text-gray-500">面积</p>
              <p class="font-medium">120 ㎡</p>
            </div>
            <div>
              <p class="text-gray-500">户型</p>
              <p class="font-medium">3室2厅</p>
            </div>
            <div>
              <p class="text-gray-500">购入价格</p>
              <p class="font-medium">¥680,000</p>
            </div>
            <div>
              <p class="text-gray-500">当前估值</p>
              <p class="font-medium text-green-600">¥810,488</p>
            </div>
          </div>
          <div
            class="flex justify-between items-center pt-3 border-t border-gray-100"
          >
            <p class="text-green-600 font-bold">
              <IconifyIconOffline
                icon="ep:arrow-up-bold"
                class="mr-0.5"
              />+19.19%
            </p>
            <button
              class="px-4 py-2 bg-orange-500 text-white text-sm rounded-lg hover:bg-orange-600"
            >
              查看详情
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
</script>

<style scoped>
.realestate-page {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
