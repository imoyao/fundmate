<template>
  <!--
    单类任务的场景句：用户选了哪一类，就只给一句「这类问题要我做什么」。
    三段式（什么情况 / 不处理会怎样 / 处理之后）已精简掉——首屏不再摊开解释。
  -->
  <p class="recon-brief">{{ meta.what }}</p>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { taskMeta, type ReconTaskKey } from "../constants/reconTasks";

defineOptions({ name: "ReconTaskBrief" });

const props = defineProps<{
  task: ReconTaskKey;
}>();

const meta = computed(() => taskMeta(props.task));
</script>

<style scoped>
/* 一句话说明与 chips 同属「筛选语境」，用行内注释承载即可；
   原先套 CardBlock 让一句话独占一张卡，把真正的待办列表顶出了首屏。 */
.recon-brief {
  padding-left: var(--space-2);
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
  border-left: 2px solid var(--border-default);
}
</style>
