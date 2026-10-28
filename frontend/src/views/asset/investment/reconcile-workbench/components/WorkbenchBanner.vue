<template>
  <!-- 柔性 Warning Banner（§6.3）：点击切换到待处理域（#1259）。
       #2716 起壳由 SoftBanner 承担；class 保留 e2e 锚点（reconcile-workbench-head.spec.ts） -->
  <SoftBanner
    class="workbench-banner"
    variant="info"
    icon="ep:warning"
    clickable
    @click="$emit('go')"
  >
    有 {{ total }} 项差异待处理，点击切换到对应域处理
  </SoftBanner>
</template>

<script setup lang="ts">
import SoftBanner from "@/components/SoftBanner/index.vue";

defineOptions({ name: "WorkbenchBanner" });

defineProps<{ total: number }>();

defineEmits<{ (e: "go"): void }>();
</script>
