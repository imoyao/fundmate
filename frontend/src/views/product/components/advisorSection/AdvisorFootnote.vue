<script setup lang="ts">
import type { AdvisorProfileResult } from "@/api/products";

/**
 * 区块脚注（#980 拆分）。
 *
 * 两条脚注是**一组**：第一条给来源与外链，第二条声明「未披露即显「—」」。
 * 间距靠共享变体 `--spaced` / `--attached` 承担，不在本组件里写
 * `:first-of-type` —— 那是把「第几条要多少间距」藏在选择器里（#2320）。
 */
defineProps<{
  profile: AdvisorProfileResult;
  /** 平台名（用户看得懂的说法；缺失时退回原始 platform 码） */
  platformLabel: string;
}>();
</script>

<template>
  <p class="section-footnote section-footnote--spaced">
    数据来源：{{ platformLabel || profile.platform }}
    <template v-if="profile.source_url">
      ·
      <a
        :href="profile.source_url"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
        class="advisor-section__link"
      >
        查看官方组合页面
      </a>
    </template>
  </p>
  <p class="section-footnote section-footnote--attached">
    组合构成与收益以平台官方披露为准；平台未披露的字段显示「—」
  </p>
</template>

<style scoped>
.advisor-section__link {
  color: var(--text-secondary);
}
</style>
