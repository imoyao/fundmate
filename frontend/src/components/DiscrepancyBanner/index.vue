<!--
  DiscrepancyBanner · 对账差异待处理横幅（挂在布局上，全局常驻）

  只显示「域 B（人工对账域）待处理」的差异，条数与落地页的「待裁决差异」一致。

  #980 批 B8 拆分后本文件只剩「外壳」：图标 / 标题 / 操作排 / 说明句 / 关闭按钮。
  - 明细行 → `DiscrepancyList.vue`
  - 取数、会话级 dismiss、路由监听 → `useDiscrepancyBanner.ts`
-->
<script setup lang="ts">
import SoftBanner from "@/components/SoftBanner/index.vue";
import { COLLAPSED_LIMIT } from "./helpers";
import { useDiscrepancyBanner } from "./useDiscrepancyBanner";
import DiscrepancyList from "./DiscrepancyList.vue";

defineOptions({ name: "DiscrepancyBanner" });

const {
  loading,
  dismissed,
  expanded,
  now,
  count,
  stalestDays,
  visibleItems,
  hiddenCount,
  routeAllowed,
  dismiss,
  goToWorkbench
} = useDiscrepancyBanner();
</script>

<template>
  <SoftBanner
    v-if="routeAllowed && !loading && !dismissed && count > 0"
    class="recon-banner"
    variant="warning"
    icon="ep:warning-filled"
    dismissible
    @close="dismiss"
  >
    <div class="recon-banner__body">
      <!-- 唯一的强调数字：待处理条数。字号走 --text-num-hero 字阶令牌（不写死 24px），
           其余数字一律用次级墨色，避免整屏都在喊。 -->
      <p class="recon-banner__title">
        有
        <span class="recon-banner__count">{{ count }}</span>
        项对账差异待处理
        <span v-if="stalestDays !== null" class="recon-banner__stalest">
          ，最久一条已挂 {{ stalestDays }} 天
        </span>
      </p>

      <DiscrepancyList :items="visibleItems" :now="now" />

      <div class="recon-banner__actions">
        <button
          type="button"
          class="recon-banner__primary"
          @click="goToWorkbench"
        >
          去对账中心处理
        </button>
        <button
          v-if="hiddenCount > 0"
          type="button"
          class="recon-banner__link"
          @click="expanded = true"
        >
          展开全部 {{ count }} 项
        </button>
        <button
          v-else-if="count > COLLAPSED_LIMIT"
          type="button"
          class="recon-banner__link"
          @click="expanded = false"
        >
          收起，仅看前 {{ COLLAPSED_LIMIT }} 项
        </button>
      </div>

      <p class="recon-banner__hint">
        差异意味着账上的数量或成本与流水推演对不上，可能影响持仓市值与收益。请到对账中心核对处理。
      </p>
    </div>
  </SoftBanner>
</template>

<style scoped>
/*
  #2716 起壳（底色/边框/图标/close 按钮）由 SoftBanner warning variant 承担，
  本文件只保留正文排版：标题 / 强调数字 / 行动排 / 说明句。
*/
.recon-banner__body {
  flex: 1 1 auto;
  min-width: 0;
}

.recon-banner__title {
  margin: 0 0 6px;
  font-size: var(--text-body, 16px);
  font-weight: 600;
  color: var(--text-primary);
}

/* 唯一的强调数字：条数。字阶走令牌（--text-num-hero 24px），
   数字等宽对齐（tabular-nums），避免刷新时宽度跳动。 */
.recon-banner__count {
  font-size: var(--text-num-hero, 24px);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  vertical-align: baseline;
  color: var(--color-warning-ink);
}

/* 次级说明：挂在标题后的「最久一条」 */
.recon-banner__stalest {
  font-size: var(--text-label, 13px);
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

.recon-banner__actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 8px;
}

/* 主行动：实底主按钮，底色 --brand-solid、文字 --text-inverse（#1600 约定的唯一组合） */
.recon-banner__primary {
  padding: 4px 12px;
  font-size: var(--text-label, 13px);
  font-weight: 600;
  color: var(--text-inverse);
  cursor: pointer;
  background: var(--brand-solid);
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: opacity 0.15s ease;
}

.recon-banner__primary:hover {
  opacity: 0.88;
}

.recon-banner__link {
  padding: 4px 2px;
  font-size: var(--text-label, 13px);
  font-weight: 600;
  color: var(--color-warning-ink);
  text-decoration: underline;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: background-color 0.15s ease;
}

.recon-banner__link:hover {
  background: var(--color-warning-20);
}

.recon-banner__hint {
  margin: 6px 0 0;
  font-size: var(--text-label, 13px);
  line-height: 20px;
  color: var(--text-tertiary-ink);
}
</style>
