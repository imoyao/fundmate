<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getGhostDuplicates, type GhostDuplicateGroup } from "@/api/summary";
import { formatDate } from "@/utils/date";
import { txnTypeLabel } from "@/constants";

const groups = ref<GhostDuplicateGroup[]>([]);
const loading = ref(true);
const dismissed = ref(false);
const expanded = ref(false);

/**
 * 收起态最多展示几组。
 *
 * ⚠️ 为什么必须截断：后端 `scan_cross_ledger_duplicates` 返回的是**全量**扁平数组，
 * 真机实测 407 组。原先模板 `v-for` 全量渲染，一张横幅被撑成几百行，把下方面内容
 * 全部顶到屏幕外——用户能做的只有「关闭」，于是这条告警实际退化成「一次性公告」：
 * 关掉就再也看不到，换台设备又原样弹回来。
 *
 * 取 5 的依据：后端已按「涉及账本数、笔数」降序排好（`summary_service.py:954`），
 * 前几条天然是最可疑的；5 行足以让用户判断「这是不是真重复」，又不会喧宾夺主。
 */
const COLLAPSED_LIMIT = 5;

const visibleGroups = computed(() =>
  expanded.value ? groups.value : groups.value.slice(0, COLLAPSED_LIMIT)
);
const hiddenCount = computed(() =>
  expanded.value ? 0 : Math.max(0, groups.value.length - COLLAPSED_LIMIT)
);
/** 只有「展开后仍然很长」才值得限高滚动：5 行以内不需要滚动条 */
const needsScroll = computed(() => expanded.value && groups.value.length > 12);

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
      <!-- 滚动容器只在展开态生效：收起态就是 5 行，套一层 overflow 会凭空
           多出滚动条与裁切风险。 -->
      <ul
        class="ghost-dup-banner__list"
        :class="{ 'ghost-dup-banner__list--scroll': needsScroll }"
      >
        <li
          v-for="(g, i) in visibleGroups"
          :key="i"
          class="ghost-dup-banner__item"
        >
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

      <!-- 处置引导（原先只有「关闭」，用户看到 407 组却无从下手）。
           这里只给可自行执行的动作，不做跳转：后端尚无 ghost 的 ignore 接口、
           对账工作台也没有对应域，硬塞一个跳转只会把用户带到看不到这批数据的页面。
           补齐后的形态见 issue「幽灵重复告警接入对账工作台」。 -->
      <div class="ghost-dup-banner__actions">
        <button
          v-if="hiddenCount > 0"
          type="button"
          class="ghost-dup-banner__link"
          @click="expanded = true"
        >
          展开全部 {{ groups.length }} 组
        </button>
        <button
          v-else-if="groups.length > COLLAPSED_LIMIT"
          type="button"
          class="ghost-dup-banner__link"
          @click="expanded = false"
        >
          收起，仅看前 {{ COLLAPSED_LIMIT }} 组
        </button>
      </div>
      <p class="ghost-dup-banner__hint">
        同一笔交易被导入到多个账本会重复计入资产与收益。请到对应账本删除其中一份
        重复记录（保留真实发生的那一份）。
      </p>
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
  color: var(--color-rise-ink);

  /* #2156 残留5：背景由品牌直调 --brand-100 改为语义错误框令牌
     --color-danger-10（底色）/ --color-danger-30（描边），与 UploadArea、
     SummaryPanel 的错误框先例一致；文字沿用 #1599 已裁决的 --color-rise-ink
     （色相 8° 同族、对比度更优）。暗色下这俩 alpha 令牌在暗底合成，轮廓不丢。 */
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
  border-radius: var(--radius-sm, 8px);
}

.ghost-dup-banner__icon {
  flex: none;
  margin-top: 2px;
  color: var(--color-rise-ink);
}

.ghost-dup-banner__body {
  flex: 1 1 auto;
  min-width: 0;
}

.ghost-dup-banner__title {
  margin: 0 0 6px;
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--color-rise-ink);
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
  color: var(--color-rise-ink);
  opacity: 0.9;
}

.ghost-dup-banner__symbol {
  font-weight: 600;
}

.ghost-dup-banner__meta,
.ghost-dup-banner__ledgers {
  opacity: 0.85;
}

/* 展开态限高滚动：407 组全量铺开会把页面撑到几百行，
   把它限制在一屏内、内部滚动，横幅仍然是一条横幅而不是一页。 */
.ghost-dup-banner__list--scroll {
  max-height: 220px;
  padding-right: 6px;
  overflow-y: auto;
}

.ghost-dup-banner__actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.ghost-dup-banner__link {
  padding: 4px 2px;
  font-size: var(--text-label, 13px);
  font-weight: 600;
  color: var(--color-rise-ink);
  text-decoration: underline;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: background-color 0.15s ease;
}

.ghost-dup-banner__link:hover {
  background: var(--color-danger-20);
}

.ghost-dup-banner__hint {
  margin: 6px 0 0;
  font-size: var(--text-label, 13px);
  line-height: 20px;
  color: var(--color-rise-ink);
  opacity: 0.8;
}

.ghost-dup-banner__close {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--color-rise-ink);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: background-color 0.15s ease;
}

.ghost-dup-banner__close:hover {
  background: var(--color-danger-20);
}
</style>
