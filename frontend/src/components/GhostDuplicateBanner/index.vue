<script setup lang="ts">
import { onMounted, ref } from "vue";
import { getGhostDuplicates, type GhostDuplicateGroup } from "@/api/summary";
import { formatDate } from "@/utils/date";
import { txnTypeLabel } from "@/constants";

const groups = ref<GhostDuplicateGroup[]>([]);
const loading = ref(true);
const dismissed = ref(false);

const STORAGE_KEY = "ghost_dup_banner_dismissed";

function isDismissed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function dismiss(): void {
  dismissed.value = true;
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* ignore */
  }
}

onMounted(async () => {
  if (isDismissed()) {
    loading.value = false;
    return;
  }
  try {
    const res = await getGhostDuplicates();
    // http 层已返回 {data,message} 信封，取一次 .data 即为载荷（此前双重解包属类型错误）
    groups.value = res.data ?? [];
  } catch {
    groups.value = [];
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div
    v-if="!loading && !dismissed && groups.length > 0"
    class="ghost-dup-banner"
    role="alert"
  >
    <div class="ghost-dup-banner__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
        <circle
          cx="12"
          cy="12"
          r="9"
          stroke="currentColor"
          stroke-width="1.6"
        />
        <path
          d="M12 7.5v5"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
        />
        <circle cx="12" cy="15.6" r="1.1" fill="currentColor" />
      </svg>
    </div>

    <div class="ghost-dup-banner__body">
      <p class="ghost-dup-banner__title">
        检测到
        {{ groups.length }}
        组疑似跨账本重复交易，可能造成资产或收益虚增，请核对。
      </p>
      <ul class="ghost-dup-banner__list">
        <li v-for="(g, i) in groups" :key="i" class="ghost-dup-banner__item">
          <span class="ghost-dup-banner__symbol">{{ g.symbol }}</span>
          <span class="ghost-dup-banner__meta">
            {{ txnTypeLabel(g.txn_type) }}
            · 金额 {{ g.amount_yuan.toLocaleString() }} 元
            <template v-if="g.confirm_date">
              · {{ formatDate(g.confirm_date) }}</template
            >
          </span>
          <span class="ghost-dup-banner__ledgers">
            出现在：{{ g.ledger_names.join("、") }}
          </span>
        </li>
      </ul>
    </div>

    <button
      type="button"
      class="ghost-dup-banner__close"
      aria-label="关闭提示"
      @click="dismiss"
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
        <path
          d="M6 6l12 12M18 6L6 18"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.ghost-dup-banner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  margin-bottom: 16px;
  color: var(--brand-700);
  background: var(--brand-100);
  border-radius: var(--radius-sm, 8px);
}

.ghost-dup-banner__icon {
  flex: none;
  margin-top: 2px;
  color: var(--brand-700);
}

.ghost-dup-banner__body {
  flex: 1 1 auto;
  min-width: 0;
}

.ghost-dup-banner__title {
  margin: 0 0 6px;
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--brand-700);
}

.ghost-dup-banner__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.ghost-dup-banner__item {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  font-size: var(--text-label, 13px);
  color: var(--brand-700);
  opacity: 0.9;
}

.ghost-dup-banner__symbol {
  font-weight: 600;
}

.ghost-dup-banner__meta,
.ghost-dup-banner__ledgers {
  opacity: 0.85;
}

.ghost-dup-banner__close {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--brand-700);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: background-color 0.15s ease;
}

.ghost-dup-banner__close:hover {
  background: var(--brand-200, rgb(246 153 136 / 20%));
}
</style>
