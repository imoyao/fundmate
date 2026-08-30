<!--
  RoadPoemBanner · 页头诗句引言卡

  保留原始设计意图：用弗罗斯特《未选择的路》为整页定调——
  「未竟之蹊」不是数据看板，而是一处让人慢下来回看的地方。
  诗句原文不做改动（原页面的核心思想），仅重排视觉层级。
-->
<template>
  <section class="poem-card">
    <div class="poem-card__quote" aria-hidden="true">
      <IconifyIconOffline icon="ep:reading" />
    </div>
    <div class="poem-card__body">
      <p class="poem-card__text">
        也许多少年后在某个地方，我会轻声叹息将往事回顾，<br />
        一片树林里分出两条路，而我选择了人迹更少的一条，<br />
        从此决定了我一生的道路。
      </p>
      <p class="poem-card__source">—— 罗伯特·弗罗斯特《未选择的路》</p>
      <p class="poem-card__lead">
        这里只留你真正在意的那几条路。慢一点回看，才看得清当初为什么出发。
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
</script>

<style scoped>
.poem-card {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 20px 24px;
  margin-bottom: 20px;
  background: var(--bg-warm);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.poem-card__quote {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  font-size: 18px;
  color: var(--brand-700);
  background: var(--brand-100);
  border-radius: 50%;
}

.poem-card__body {
  flex: 1;
  min-width: 0;
}

.poem-card__text {
  font-family: Georgia, "Songti SC", "Noto Serif SC", serif;
  font-size: 14px;
  font-style: italic;
  line-height: 2;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.poem-card__source {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.poem-card__lead {
  padding-top: 12px;
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  border-top: 1px solid var(--border-subtle);
}
</style>
