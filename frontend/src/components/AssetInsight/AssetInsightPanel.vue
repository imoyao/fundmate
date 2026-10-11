<template>
  <!-- 资产透视区块：产品类型分布 + 配置目标（五笔钱）分布两张环形图。
       设计系统强制复用：SectionHeader（区块标题）+ CardBlock（卡片容器）。
       颜色/样式全部走 design.md 语义变量，禁止硬编码。 -->
  <CardBlock>
    <SectionHeader
      title="资产透视"
      info="基于持仓与资产的多维聚合，一眼看清资产结构与基金配置"
    />
    <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <!-- 标题必须点明维度，且与该环实际消费的字段一致（#2032）：
           左环绘 `type_distribution`（后端按 `asset_type` 聚合，键为 `TYPE_LABELS`），
           写「资产分布」是漏维度的泛称——本页另有三处也自称「资产分布」；
           右环绘 `allocation_distribution`（键为五笔钱 `ALLOCATION_LABELS`），
           写「基金类型分布」是名实不符，该字段与「基金是哪一类」无关。 -->
      <AssetAllocationDonut
        title="产品类型分布"
        :data="assetDist"
        :loading="loading"
      />
      <AssetAllocationDonut
        title="配置目标（五笔钱）分布"
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

// 变量名跟随字段语义：`type_distribution` 是产品类型，不是「资产分布」
const assetDist = computed(() => distributions.value?.type_distribution ?? []);
// `allocation_distribution` 是五笔钱 / 配置目标，不是「基金类型」
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
