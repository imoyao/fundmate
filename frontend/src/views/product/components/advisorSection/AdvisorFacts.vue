<script setup lang="ts">
import type { AdvisorProfileResult } from "@/api/products";
import { DASH } from "./advisorModel";

/**
 * 投顾组合的识别信息（#980 拆分）。
 *
 * 不展示代码（设计 §2.6）：组合类标的靠「名称 + 平台 + 机构」识别。
 * ⚠️ 设计要求写的是「平台/主理人」，但主理人实测填充率只有 1.9%，
 * 故实际锚点落在**机构**（100%）上 —— 不为凑条文编造。
 */
defineProps<{
  profile: AdvisorProfileResult;
  /** 平台名（已由 getAdvisorPlatformLabel 归一，取不到时为空串） */
  platformLabel: string;
}>();
</script>

<template>
  <dl class="facts-grid">
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">组合名称</dt>
      <dd class="facts-grid__value facts-grid__value--strong">
        {{ profile.name || DASH }}
      </dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">平台</dt>
      <dd class="facts-grid__value">{{ platformLabel || DASH }}</dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">机构</dt>
      <dd class="facts-grid__value facts-grid__value--wrap">
        {{ profile.org_name || DASH }}
      </dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">主理人</dt>
      <dd class="facts-grid__value">{{ profile.host || DASH }}</dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">风险等级</dt>
      <dd class="facts-grid__value">
        {{ profile.risk_level || DASH }}
      </dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">产品类型</dt>
      <dd class="facts-grid__value">
        {{ profile.product_type || DASH }}
      </dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">成立日期</dt>
      <dd class="facts-grid__value">
        {{ profile.estab_date || DASH }}
      </dd>
    </div>
    <div class="facts-grid__cell">
      <dt class="facts-grid__label">最新净值</dt>
      <dd class="facts-grid__value">
        <template v-if="profile.nav != null">
          {{ profile.nav.toFixed(4) }}
        </template>
        <template v-else>{{ DASH }}</template>
        <span v-if="profile.nav_date" class="advisor-section__sub">
          （{{ profile.nav_date }}）
        </span>
      </dd>
    </div>
  </dl>
</template>

<style lang="scss" scoped>
@use "./advisor-base";
</style>
