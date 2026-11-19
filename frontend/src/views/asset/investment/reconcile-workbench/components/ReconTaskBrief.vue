<template>
  <!--
    单类任务的场景句：用户选了哪一类，就只给一句「这类问题要我做什么」。
    三段式（什么情况 / 不处理会怎样 / 处理之后）已精简掉——首屏不再摊开解释。
  -->
  <CardBlock class="recon-brief">
    <p class="recon-brief__scene">{{ meta.what }}</p>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { taskMeta, type ReconTaskKey } from "../constants/reconTasks";

defineOptions({ name: "ReconTaskBrief" });

const props = defineProps<{
  task: ReconTaskKey;
}>();

const meta = computed(() => taskMeta(props.task));
</script>

<style scoped>
.recon-brief {
  margin-bottom: var(--space-compact);
}

.recon-brief__scene {
  margin: 0;
  font-size: var(--text-small);
  line-height: 1.7;
  color: var(--text-secondary);
}
</style>
