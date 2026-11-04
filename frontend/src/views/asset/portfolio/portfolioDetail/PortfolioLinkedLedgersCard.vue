<script setup lang="ts">
import { useRouter } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { type LinkedLedger, ledgerTypeLabel } from "./portfolioDetailModel";
import PortfolioTableEmpty from "./PortfolioTableEmpty.vue";

/**
 * 关联账户表：账户名 / 账户类型 / 跳账户详情。
 *
 * 只有展示与一次路由跳转，故整块成组件；`ledgerTypeLabel` 是纯函数（在 model 里），
 * 从父层搬走后仍是「零响应式」的一行判断（#980）。
 */
defineOptions({ name: "PortfolioLinkedLedgersCard" });

defineProps<{
  ledgers: LinkedLedger[];
}>();

const router = useRouter();

function goToLedger(id: number) {
  router.push(`/asset/ledgers/${id}`);
}
</script>

<template>
  <CardBlock>
    <SectionHeader title="关联账户" />
    <el-table v-if="ledgers.length" :data="ledgers" stripe size="default">
      <el-table-column prop="name" label="账户名称" min-width="150" />
      <el-table-column label="账户类型" width="120">
        <template #default="{ row }">
          {{ ledgerTypeLabel(row.ledger_type) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button text size="small" @click="goToLedger(row.id)"
            >查看</el-button
          >
        </template>
      </el-table-column>
    </el-table>
    <PortfolioTableEmpty v-else>
      暂无账户关联此组合，请在账户编辑中选择关联。
    </PortfolioTableEmpty>
  </CardBlock>
</template>
