<template>
  <!-- 阶段面板的纯导航列表（漏斗，2026-11-13）：只列组，不做写操作、
       不做二次筛选、不弹弹窗——动作唯一入口在抽屉执行区（ReconItemAction）。
       `groups` 已由 ReconStagePanel 用 bucketByStage 按阶段筛好。 -->
  <div class="domain-f-body">
    <ReconStatusState
      :loading="loading"
      :error="error || null"
      :empty="!loading && !error && groups.length === 0"
      @retry="emit('retry')"
    >
      <template #empty>
        <el-empty description="暂无数据缺失" :image-size="80" />
      </template>
      <div class="df-groups">
        <DanglingRefGroupCard
          v-for="g in groups"
          :key="g.key"
          :group="g"
          @open-item="emit('openItem', $event)"
        />
      </div>
    </ReconStatusState>
  </div>
</template>

<script setup lang="ts">
import type { DanglingRefGroup } from "@/api/reconciliation";
import DanglingRefGroupCard from "./DanglingRefGroupCard.vue";
import ReconStatusState from "./ReconStatusState.vue";

defineOptions({ name: "DomainFDanglingRefs" });

withDefaults(
  defineProps<{
    groups: DanglingRefGroup[];
    loading: boolean;
    error?: string;
  }>(),
  { error: "" }
);

const emit = defineEmits<{
  openItem: [group: DanglingRefGroup];
  retry: [];
}>();
</script>

<style scoped>
.domain-f-body {
  padding: 4px 0;
}

.df-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
