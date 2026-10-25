<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";

/**
 * 货币基金收益（组合维度：按 ledger_id 聚合关联账户；与 XIRR 并列，不与 XIRR 相加）。
 * 标题与复盘页「货币基金收益」同词（2026-10-25 由「货基收益」改名统一叫法）。
 *
 * 自含取数：进入详情页即自动拉一次，卡片头部的「刷新」重拉。父层只传 portfolioId，
 * 因此 `v-if="moneyFundData || moneyFundLoading"` 也留在本组件根节点上——数据没回来
 * 且未在加载时整块不渲染（与拆分前一致）。
 *
 * `.xirr-*` 样式不在这里：它们由父页的 `:deep()` 覆盖「组合收益卡 + 货基卡」两张卡，
 * 搬进任一张卡都会让另一张失去样式（见父页样式注释）。
 */
defineOptions({ name: "PortfolioMoneyFundCard" });

const props = defineProps<{
  portfolioId: number;
}>();

const moneyFundData = ref<MoneyFundIncomeData | null>(null);
const moneyFundLoading = ref(false);

async function fetchMoneyFund() {
  moneyFundLoading.value = true;
  try {
    const res = await getMoneyFundIncome({
      scope: "portfolio",
      portfolio_id: props.portfolioId
    });
    moneyFundData.value = res.data;
  } catch {
    ElMessage.error("获取货币基金收益失败");
  } finally {
    moneyFundLoading.value = false;
  }
}

onMounted(fetchMoneyFund);
</script>

<template>
  <CardBlock v-if="moneyFundData || moneyFundLoading" class="mb-6">
    <SectionHeader title="货币基金收益">
      <template #action>
        <el-button
          size="small"
          :loading="moneyFundLoading"
          @click="fetchMoneyFund"
        >
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
        </el-button>
      </template>
    </SectionHeader>
    <div v-if="moneyFundData" class="xirr-grid">
      <div class="xirr-item">
        <span class="xirr-label">近30天累计</span>
        <div class="xirr-value">
          <MoneyDisplay :value="moneyFundData.total_income" />
        </div>
      </div>
      <div class="xirr-item xirr-item--ml">
        <span class="xirr-label">今日收益</span>
        <div class="xirr-value">
          <MoneyDisplay :value="moneyFundData.today_income" :show-sign="true" />
        </div>
      </div>
    </div>
    <div v-else-if="!moneyFundLoading" class="xirr-empty">
      点击刷新获取货币基金收益
    </div>
    <div v-else class="xirr-empty">计算中...</div>
  </CardBlock>
</template>
