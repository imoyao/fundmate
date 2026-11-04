<script setup lang="ts">
import { computed } from "vue";
import type { ManagerProfileResult } from "@/api/products";
import { productRoute } from "@/utils/productIdentity";
import { fundsTruncated, tenureSpan } from "./mgrModel";

/**
 * 任职基金列表（#980 拆分）。
 *
 * 两条口径不能改：
 * - 在任标记以 F10 任期为准（`is_active`）：东财全量表把已卸任者仍列为现任，
 *   直接信它会给用户「此人还在管这只」的错觉；
 * - 任期跨度空起始日整段不渲染，不显示「— ~ —」。
 */
const props = defineProps<{
  profile: ManagerProfileResult;
}>();

const truncated = computed(() => fundsTruncated(props.profile));
</script>

<template>
  <div v-if="profile.funds.length" class="mgr-section__funds">
    <h4 class="mgr-section__subtitle">任职基金</h4>
    <ul class="mgr-section__fund-list">
      <li
        v-for="f in profile.funds"
        :key="f.fund_code"
        class="mgr-section__fund-item"
      >
        <RouterLink
          class="mgr-section__fund-link"
          :to="productRoute({ assetType: 'fund', symbol: f.fund_code })"
        >
          {{ f.name }}
        </RouterLink>
        <span class="mgr-section__fund-meta">
          <!-- 任期跨度：起始 ~ 结束（在任则到今天）。空值不渲染，不显示「— ~ —」 -->
          <span v-if="f.start_date" class="mgr-section__fund-tenure">
            {{ tenureSpan(f.start_date, f.end_date) }}
          </span>
          <span v-if="f.tenure_display" class="mgr-section__fund-tenure-length">
            {{ f.tenure_display.text }}
          </span>
          <!-- 在任标记以 F10 任期为准：东财全量表把已卸任者仍列为现任 -->
          <span
            v-if="!f.is_active"
            class="mgr-section__badge mgr-section__badge--muted"
          >
            已卸任
          </span>
          <span v-else-if="f.is_classic" class="mgr-section__badge"
            >代表作</span
          >
        </span>
      </li>
    </ul>
    <p v-if="truncated" class="mgr-section__note">
      共 {{ profile.fund_count }} 只，当前仅显示前
      {{ profile.funds.length }} 只。
    </p>
  </div>
  <p v-else class="mgr-section__hint">暂无关联的任职基金</p>
</template>

<style lang="scss" scoped>
@use "./mgr-base";
</style>
