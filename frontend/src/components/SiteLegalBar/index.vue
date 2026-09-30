<!--
  SiteLegalBar · 全站「法律底栏」单一来源（footer 去耦，#1720 衍生）
  把散落在 lay-footer 与 PageFooter 的「合规免责 + 版权 + 系统状态入口 + 开源致谢」
  收敛到一处，消除双重维护与文案不一致：
    - 合规免责文案：单一常量
    - 版权主体「© 2026 多多贝」：单一常量（年份跨年只需改此处）
    - 系统状态入口：单一路由常量（/system/status）
    - 开源致谢：可选外链（仅全局布局页展示）
  props:
    - brandSuffix:        版权尾缀（如「· 让投资更从容」），可选
    - acknowledgementHref: 非空则展示「开源致谢」外链（默认空，不展示）
-->
<template>
  <div class="site-legal-bar">
    <span class="site-legal-bar__disclaimer">{{ DISCLAIMER }}</span>
    <span class="site-legal-bar__sep" aria-hidden="true">·</span>
    <span class="site-legal-bar__copyright"
      >{{ COPYRIGHT_BASE
      }}<template v-if="brandSuffix"> {{ brandSuffix }}</template></span
    >
    <template v-if="acknowledgementHref">
      <span class="site-legal-bar__sep" aria-hidden="true">·</span>
      <a
        class="site-legal-bar__link"
        :href="acknowledgementHref"
        target="_blank"
        rel="noopener noreferrer"
        >开源致谢</a
      >
    </template>
    <span class="site-legal-bar__sep" aria-hidden="true">·</span>
    <router-link class="site-legal-bar__link" :to="SYSTEM_STATUS_TO"
      >系统状态</router-link
    >
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    brandSuffix?: string;
    acknowledgementHref?: string;
  }>(),
  {
    brandSuffix: "",
    acknowledgementHref: ""
  }
);

// 单一来源：合规免责文案
const DISCLAIMER =
  "市场有风险，投资需谨慎。本平台内容仅供参考，不构成任何投资建议。";
// 单一来源：版权主体（年份跨年只需改此处）
const COPYRIGHT_BASE = "© 2026 多多贝";
// 单一来源：系统状态页入口（#1802 起路径为 /status；API 仍是 /api/health）
const SYSTEM_STATUS_TO = "/status";
</script>

<style lang="scss" scoped>
.site-legal-bar {
  display: flex;
  flex-flow: row wrap;
  gap: 4px 8px;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary-ink);
  text-align: center;
  white-space: normal;

  &__disclaimer,
  &__copyright {
    color: var(--text-tertiary-ink);
  }

  &__sep {
    color: var(--border-default);
  }

  &__link {
    color: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;

    &:hover {
      color: var(--text-primary);
    }
  }
}
</style>
