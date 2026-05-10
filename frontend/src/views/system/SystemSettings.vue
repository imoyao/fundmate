<template>
  <div class="system-settings p-6">
    <div class="mb-8">
      <h2 class="text-2xl font-bold">系统设置</h2>
      <p class="text-gray-500 mt-1">配置系统参数和个人偏好</p>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden">
      <div class="p-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div>
            <h3 class="text-base font-bold mb-5">显示设置</h3>
            <div class="space-y-5">
              <div class="flex items-center justify-between">
                <div>
                  <p class="font-medium text-sm">深色模式</p>
                  <p class="text-xs text-gray-500">切换界面明暗主题</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input
                    v-model="settings.darkMode"
                    type="checkbox"
                    class="sr-only peer"
                  />
                  <div
                    class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-500"
                  />
                </label>
              </div>

              <div class="flex items-center justify-between">
                <div>
                  <p class="font-medium text-sm">显示风险标签</p>
                  <p class="text-xs text-gray-500">在资产卡片上显示风险等级</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input
                    v-model="settings.showRiskTag"
                    type="checkbox"
                    class="sr-only peer"
                    checked
                  />
                  <div
                    class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-500"
                  />
                </label>
              </div>

              <div>
                <p class="font-medium text-sm mb-2">默认时间范围</p>
                <select
                  v-model="settings.defaultTimeRange"
                  class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
                >
                  <option value="month">本月</option>
                  <option value="quarter">近3个月</option>
                  <option value="halfYear">近6个月</option>
                  <option value="year">本年</option>
                </select>
              </div>
            </div>
          </div>

          <div>
            <h3 class="text-base font-bold mb-5">通知设置</h3>
            <div class="space-y-5">
              <div class="flex items-center justify-between">
                <div>
                  <p class="font-medium text-sm">价格提醒</p>
                  <p class="text-xs text-gray-500">资产价格大幅波动时通知</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input
                    v-model="settings.priceAlert"
                    type="checkbox"
                    class="sr-only peer"
                    checked
                  />
                  <div
                    class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-500"
                  />
                </label>
              </div>

              <div class="flex items-center justify-between">
                <div>
                  <p class="font-medium text-sm">交易确认</p>
                  <p class="text-xs text-gray-500">交易完成后发送确认通知</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input
                    v-model="settings.transactionConfirm"
                    type="checkbox"
                    class="sr-only peer"
                    checked
                  />
                  <div
                    class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-500"
                  />
                </label>
              </div>

              <div>
                <p class="font-medium text-sm mb-2">波动阈值</p>
                <div class="flex items-center gap-4">
                  <input
                    v-model="settings.volatilityThreshold"
                    type="range"
                    min="1"
                    max="10"
                    class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                  />
                  <span class="font-medium text-orange-500 text-sm min-w-[50px]"
                    >{{ settings.volatilityThreshold }}%</span
                  >
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-8 pt-6 border-t border-gray-200 flex justify-end gap-3">
          <button
            class="px-5 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors shadow-sm"
          >
            重置
          </button>
          <button
            class="px-5 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 transition-colors shadow-sm"
            @click="saveSettings"
          >
            保存设置
          </button>
        </div>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md overflow-hidden mt-6">
      <div class="p-6">
        <h3 class="text-base font-bold mb-5">账户管理</h3>
        <div class="space-y-3">
          <div
            class="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div class="flex items-center">
              <div
                class="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center mr-3"
              >
                <IconifyIconOffline icon="ep:user" class="text-orange-500" />
              </div>
              <div>
                <p class="font-medium text-sm">账户持有人</p>
                <p class="text-xs text-gray-500">张小明</p>
              </div>
            </div>
            <button class="text-orange-500 text-sm hover:underline">
              修改
            </button>
          </div>

          <div
            class="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div class="flex items-center">
              <div
                class="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center mr-3"
              >
                <IconifyIconOffline icon="ep:shield" class="text-green-500" />
              </div>
              <div>
                <p class="font-medium text-sm">登录密码</p>
                <p class="text-xs text-gray-500">上次修改：2024-01-15</p>
              </div>
            </div>
            <button class="text-orange-500 text-sm hover:underline">
              修改
            </button>
          </div>

          <div
            class="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div class="flex items-center">
              <div
                class="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mr-3"
              >
                <IconifyIconOffline icon="ep:bell" class="text-blue-500" />
              </div>
              <div>
                <p class="font-medium text-sm">通知方式</p>
                <p class="text-xs text-gray-500">邮件 + 短信</p>
              </div>
            </div>
            <button class="text-orange-500 text-sm hover:underline">
              修改
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { ElMessage } from "element-plus";

const settings = reactive({
  darkMode: false,
  showRiskTag: true,
  defaultTimeRange: "month",
  priceAlert: true,
  transactionConfirm: true,
  volatilityThreshold: 5
});

const saveSettings = () => {
  ElMessage.success("设置已保存");
};
</script>

<style scoped>
.system-settings {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
