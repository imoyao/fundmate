<template>
  <!-- 资产透视区块（Issue #1014）：资产分布 + 基金类型分布两张环形图。
       设计系统强制复用：SectionHeader（区块标题）+ CardBlock（卡片容器）。
       颜色/样式全部走 design.md 语义变量，禁止硬编码。 -->
  <CardBlock>
    <SectionHeader
      title="资产透视"
      info="基于持仓与资产的多维聚合，一眼看清资产结构与基金配置"
    />
    <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <AssetAllocationDonut
        title="资产分布"
        :data="assetDist"
        :loading="loading"
      />
      <AssetAllocationDonut
        title="基金类型分布"
        :data="fundTypeDist"
        :loading="loading"
      />
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import { getDistributions, type DistributionsData } from "@/api/summary";

defineOptions({ name: "AssetInsightPanel" });

// 自包含数据：复用现有聚合出口，无需父组件透传
const distributions = ref<DistributionsData | null>(null);
const loading = ref(false);

const assetDist = computed(() => distributions.value?.type_distribution ?? []);
const fundTypeDist = computed(
  () => distributions.value?.allocation_distribution ?? []
);

async function load() {
  loading.value = true;
  try {
    const res = await getDistributions();
    distributions.value = res.data ?? null;
  } catch {
    distributions.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
