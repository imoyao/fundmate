<template>
  <div class="recon-stage">
    <!-- 单组执行区（漏斗 §3.4）：返回路径 + 动作。动作唯一入口在执行区，
         面板自身不做任何写操作；弹窗由 ReconItemAction 自包含。 -->
    <template v-if="focusedItem">
      <el-button
        class="recon-stage__back"
        size="small"
        text
        @click="clearFocus"
      >
        返回阶段列表
      </el-button>
      <ReconItemAction
        :item="focusedItem"
        @fix-dangling="emit('fixDangling', $event)"
        @refresh="emit('refresh', $event)"
      />
    </template>

    <!-- 阶段导航：按 DANGLING_STAGES 固定顺序只渲染有组的段，
         空阶段整段不渲染（不渲染空标题、不渲染占位）。 -->
    <template v-else>
      <section
        v-for="seg in segments"
        :key="seg.stage"
        class="recon-stage__seg"
      >
        <SectionHeader :title="danglingStageHeading(seg.stage, seg.groups)" />
        <DomainFDanglingRefs
          :groups="seg.groups"
          :loading="loading"
          :error="error"
          @open-item="focusGroup(seg.stage, $event)"
          @retry="emit('retry')"
        />
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DanglingRefGroup } from "@/api/reconciliation";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { DanglingStage } from "../utils/danglingRefEnrichScope";
import { DANGLING_STAGES } from "../utils/danglingRefEnrichScope";
import { danglingStageHeading, danglingStageItem } from "../utils/reconQueue";
import type { ReconQueueItem } from "../utils/reconQueue";
import DomainFDanglingRefs from "./DomainFDanglingRefs.vue";
import ReconItemAction from "./ReconItemAction.vue";

defineOptions({ name: "ReconStagePanel" });

const props = defineProps<{
  /** 非空 = 单阶段面板（点队列聚合项进来）；null = ?domain=F 全量形态 */
  stage: DanglingStage | null;
  /** 全部组按阶段分桶（ReconQueueDetail 用 bucketByStage 算好，本组件不重算） */
  buckets: Record<DanglingStage, DanglingRefGroup[]>;
  loading: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  /** 聚焦单组 / 退回导航时上抛合成队列项，供抽屉头部、轨迹、来龙去脉切换 */
  "update:focusItem": [item: ReconQueueItem | null];
  fixDangling: [group: DanglingRefGroup];
  refresh: [key: string];
  retry: [];
}>();

interface StageSegment {
  stage: DanglingStage;
  groups: DanglingRefGroup[];
}

/** 要渲染的阶段段：单阶段模式只看该阶段；全量模式按固定顺序取有组的段 */
const segments = computed<StageSegment[]>(() => {
  if (props.stage) {
    const groups = props.buckets[props.stage];
    return groups.length ? [{ stage: props.stage, groups }] : [];
  }
  return DANGLING_STAGES.filter(stage => props.buckets[stage].length > 0).map(
    stage => ({ stage, groups: props.buckets[stage] })
  );
});

/** 聚焦的是组的 key（组卡稳定键），合成项由 danglingStageItem 现算 */
const focusKey = ref<string | null>(null);
const focusedItem = computed<ReconQueueItem | null>(() => {
  if (focusKey.value === null) return null;
  for (const seg of segments.value) {
    const group = seg.groups.find(g => g.key === focusKey.value);
    if (group) return danglingStageItem(seg.stage, [group]);
  }
  return null;
});

function focusGroup(stage: DanglingStage, group: DanglingRefGroup): void {
  focusKey.value = group.key;
  emit("update:focusItem", danglingStageItem(stage, [group]));
}

/** 返回阶段列表：只清本地聚焦，不动 activeStage（阶段面板还在） */
function clearFocus(): void {
  if (focusKey.value === null) return;
  focusKey.value = null;
  emit("update:focusItem", null);
}

/** 聚焦的组被处理掉（回补 / 删除后 buckets 刷新）就自动退回导航，不留死引用 */
watch(segments, segs => {
  if (
    focusKey.value !== null &&
    !segs.some(seg => seg.groups.some(g => g.key === focusKey.value))
  ) {
    clearFocus();
  }
});
</script>

<style scoped>
.recon-stage__seg + .recon-stage__seg {
  margin-top: var(--space-standard);
}

.recon-stage__back {
  margin-bottom: var(--space-compact);
}
</style>
