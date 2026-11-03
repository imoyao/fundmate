<!--
  策略洞察区块（目标配比 / 策略诊断 / 持仓小贴士）· 默认收起、首次展开才取数。

  为什么折起来（2026-11-03）：这三块都是规则对持仓给出的**判断**，而所属页面
  （全面盘点）的定位是「把已经发生的事落库，不产生判断」
  （`docs/design/navigation-ia.md`）。此前它们以三张满高卡片常驻，把一个录入
  工作台撑成分析页，录入动线（选大类 → 记一笔 → 看明细）被挤到三屏以外。

  为什么不迁去「资产概览」：目标配比可编辑（写库），而那个顶级的定义是**纯读**。
  留在本页折叠、懒加载，是同时满足两条约束成本最低的解。

  数据层仍复用 `useStrategyInsight`（本组件自己调用，故请求随组件挂载策略走：
  收起时一个引擎接口都不打，只有「记账成功」这类全局刷新会顺带重取）。
-->
<template>
  <section class="inventory-section">
    <SectionHeader
      title="策略洞察"
      info="目标配比 / 策略诊断 / 持仓小贴士——由规则对你的持仓算出的结论，与录入无关，默认收起。"
    >
      <template #action>
        <el-button text size="small" :aria-expanded="open" @click="toggle">
          {{ open ? "收起" : "展开" }}
          <IconifyIconOffline
            :icon="open ? 'ep:arrow-up' : 'ep:arrow-down'"
            class="ml-1"
          />
        </el-button>
      </template>
    </SectionHeader>

    <el-collapse-transition>
      <div v-show="open" class="insight-stack">
        <AllocationTargetCard
          :data="allocation"
          :loading="allocationLoading"
          :error="allocationError"
          :saving="allocationSaving"
          :reminder-refreshing="reminderRefreshing"
          @save="saveTargets"
          @refresh-reminders="refreshReminders"
          @retry="loadAllocation"
        />
        <StrategyDiagnosisCard
          :diagnosis="diagnosis"
          :behavior="behavior"
          :strategies="strategies"
          :loading="diagnosisLoading"
          :error="diagnosisError"
          @retry="loadDiagnosis"
        />
        <RuleTipsCard />
      </div>
    </el-collapse-transition>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { useStrategyInsight } from "../useInventoryData";
import AllocationTargetCard from "./AllocationTargetCard.vue";
import RuleTipsCard from "./RuleTipsCard.vue";
import StrategyDiagnosisCard from "./StrategyDiagnosisCard.vue";

defineOptions({ name: "StrategyInsightSection" });

const {
  allocation,
  allocationLoading,
  allocationError,
  allocationSaving,
  reminderRefreshing,
  diagnosis,
  behavior,
  strategies,
  diagnosisLoading,
  diagnosisError,
  loadStrategyInsight,
  loadAllocation,
  loadDiagnosis,
  saveTargets,
  refreshReminders
} = useStrategyInsight();

const open = ref(false);

function toggle() {
  open.value = !open.value;
  if (open.value) void loadStrategyInsight();
}
</script>

<style scoped>
/* 三张卡纵向排列：间距与页面 shell 的区块间距一致（此前各占一个独立 section） */
.insight-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
}
</style>
