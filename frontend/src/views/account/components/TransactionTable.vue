<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 mb-6">
    <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
      最近交易记录
    </h3>
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-700">
          <tr>
            <th
              scope="col"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              交易类型
            </th>
            <th
              scope="col"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              金额
            </th>
            <th
              scope="col"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              日期
            </th>
            <th
              scope="col"
              class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              描述
            </th>
          </tr>
        </thead>
        <tbody
          class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700"
        >
          <tr v-for="transaction in transactions" :key="transaction.id">
            <td
              class="px-6 py-4 whitespace-nowrap text-sm font-medium"
              :class="{
                'text-green-600': transaction.type === '收入',
                'text-red-600': transaction.type === '支出'
              }"
            >
              {{ transaction.type }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white"
            >
              {{ transaction.amount }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400"
            >
              {{ transaction.date }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400"
            >
              {{ transaction.description }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const transactions = ref([
  {
    id: 1,
    type: "收入",
    amount: "+¥ 5,000.00",
    date: "2023-10-26",
    description: "工资入账"
  },
  {
    id: 2,
    type: "支出",
    amount: "-¥ 1,200.00",
    date: "2023-10-25",
    description: "购买股票"
  },
  {
    id: 3,
    type: "收入",
    amount: "+¥ 200.00",
    date: "2023-10-24",
    description: "基金分红"
  },
  {
    id: 4,
    type: "支出",
    amount: "-¥ 300.00",
    date: "2023-10-23",
    description: "生活消费"
  },
  {
    id: 5,
    type: "收入",
    amount: "+¥ 1,000.00",
    date: "2023-10-22",
    description: "兼职收入"
  }
]);
</script>

<style scoped>
/* 可以添加一些组件特有的样式 */
</style>
