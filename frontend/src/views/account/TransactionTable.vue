<template>
  <div class="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
    <h2 class="text-xl font-semibold mb-4 text-gray-800 dark:text-white">
      最近交易记录
    </h2>
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
          <tr v-for="(transaction, index) in transactions" :key="index">
            <td
              class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white"
            >
              {{ transaction.type }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300"
            >
              {{ transaction.amount }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300"
            >
              {{ transaction.date }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-300"
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
    type: "买入",
    amount: "-¥1,200.00",
    date: "2023-10-26",
    description: "购买腾讯股票"
  },
  {
    type: "卖出",
    amount: "+¥500.00",
    date: "2023-10-25",
    description: "出售部分阿里巴巴股票"
  },
  {
    type: "分红",
    amount: "+¥80.00",
    date: "2023-10-24",
    description: "基金分红"
  },
  {
    type: "买入",
    amount: "-¥3,000.00",
    date: "2023-10-23",
    description: "购买易方达消费精选基金"
  },
  {
    type: "充值",
    amount: "+¥10,000.00",
    date: "2023-10-22",
    description: "银行转账充值"
  }
]);
</script>

<style scoped>
/* Add any specific styles for this component here if needed */
</style>
