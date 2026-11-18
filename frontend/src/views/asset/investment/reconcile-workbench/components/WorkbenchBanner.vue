<template>
  <!-- 柔性提示条：点击落到有待办的那一类任务并定位到队列。
       壳由 SoftBanner 承担；class 保留 e2e 锚点（reconcile-workbench-head.spec.ts）。
       文案不再说「切换到对应域」——域是后端概念，用户要找的是待办。 -->
  <SoftBanner
    class="workbench-banner"
    variant="info"
    icon="ep:warning"
    clickable
    @click="$emit('go')"
  >
    有 {{ total }} 项差异待处理，点击查看待办
  </SoftBanner>
</template>

<script setup lang="ts">
import SoftBanner from "@/components/SoftBanner/index.vue";

defineOptions({ name: "WorkbenchBanner" });

defineProps<{ total: number }>();

defineEmits<{ (e: "go"): void }>();
</script>
