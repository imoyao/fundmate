<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-6">
    <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
      账户概览
    </h3>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- 账户信息 -->
      <div>
        <h4 class="text-md font-medium mb-2 text-gray-800 dark:text-gray-200">
          账户信息
        </h4>
        <div class="space-y-2 text-gray-700 dark:text-gray-300">
          <p><strong>账户名:</strong> {{ accountInfo.name }}</p>
          <p><strong>账户ID:</strong> {{ accountInfo.id }}</p>
          <p><strong>开户日期:</strong> {{ accountInfo.openingDate }}</p>
          <p><strong>联系邮箱:</strong> {{ accountInfo.email }}</p>
        </div>
      </div>

      <!-- 资金状况 -->
      <div>
        <h4 class="text-md font-medium mb-2 text-gray-800 dark:text-gray-200">
          资金状况
        </h4>
        <div class="space-y-2 text-gray-700 dark:text-gray-300">
          <p>
            <strong>可用余额:</strong>
            <span class="font-bold text-green-600">{{
              fundStatus.availableBalance
            }}</span>
          </p>
          <p><strong>冻结资金:</strong> {{ fundStatus.frozenFunds }}</p>
          <p>
            <strong>总资产:</strong>
            <span class="font-bold text-blue-600">{{
              fundStatus.totalAssets
            }}</span>
          </p>
          <p>
            <strong>今日盈亏:</strong>
            <span
              :class="[
                fundStatus.dailyPnl.includes('-')
                  ? 'text-red-600'
                  : 'text-green-600',
                'font-bold'
              ]"
              >{{ fundStatus.dailyPnl }}</span
            >
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const accountInfo = ref({
  name: "张三",
  id: "123456789",
  openingDate: "2022-01-01",
  email: "zhangsan@example.com"
});

const fundStatus = ref({
  availableBalance: "¥ 50,000.00",
  frozenFunds: "¥ 5,000.00",
  totalAssets: "¥ 730,000.00",
  dailyPnl: "+¥ 1,200.00"
});
</script>

<style scoped>
/* 可以添加一些组件特有的样式 */
</style>
