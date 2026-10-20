<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listDiscrepancies, type DiscrepancyItem } from "@/api/reconciliation";
import { getMe } from "@/api/auth";
import { discrepancyTypeLabel } from "@/constants";
import { formatDiff } from "@/views/asset/investment/reconcile-workbench/utils/discFormat";
import {
  ageLabel,
  COLLAPSED_LIMIT,
  pendingDays,
  pickDomainBPending,
  shouldShowOnRoute,
  sortByStaleness,
  WORKBENCH_ROUTE_NAME
} from "./helpers";

defineOptions({ name: "DiscrepancyBanner" });

const route = useRoute();
const router = useRouter();

/** 域 B 待处理差异（已按「挂得最久」排序） */
const pending = ref<DiscrepancyItem[]>([]);
const loading = ref(true);
const dismissed = ref(false);
const expanded = ref(false);

/**
 * 计算「挂了几天」所依据的基准时刻。
 *
 * 固定在取数那一刻，而不是每次渲染都 `new Date()`：一是模板里反复 new Date
 * 会让同一批数据算出跨天不一致的结果，二是渲染期的隐式时间依赖无法测试。
 */
const now = ref(new Date());

/** 本次会话是否已关闭（sessionStorage，key 带 family_id） */
const STORAGE_KEY = "recon_pending_banner_dismissed";

/**
 * 按家庭隔离的 dismiss key。
 *
 * 与 `GhostDuplicateBanner` 同口径：单一常量 key 会让换家庭 / 换账号共用同一个开关
 * （语义错误），且「拿不到 family 时退化为无后缀 key」——宁可隔离失效，也不要开关失效。
 */
function dismissKey(familyId: number | null): string {
  return familyId == null ? STORAGE_KEY : `${STORAGE_KEY}:${familyId}`;
}

/** 已登录取到的家庭 id（模块内缓存，避免每张页面都打一次 /me） */
let cachedFamilyId: number | null | undefined;

async function resolveFamilyId(): Promise<number | null> {
  if (cachedFamilyId !== undefined) return cachedFamilyId;
  try {
    const res = await getMe();
    cachedFamilyId = res.data?.family?.id ?? null;
  } catch {
    cachedFamilyId = null;
  }
  return cachedFamilyId;
}

function isDismissed(familyId: number | null): boolean {
  try {
    return sessionStorage.getItem(dismissKey(familyId)) === "1";
  } catch {
    return false;
  }
}

function dismiss(): void {
  dismissed.value = true;
  void resolveFamilyId().then(fid => {
    try {
      sessionStorage.setItem(dismissKey(fid), "1");
    } catch {
      /* ignore */
    }
  });
}

/** 拉取域 B 待处理差异并按「挂得最久」排序 */
async function loadPending(): Promise<void> {
  try {
    const res = await listDiscrepancies({ status: "pending" });
    // 只取域 B（口径说明见 helpers.pickDomainBPending），并按「挂得最久」排序
    now.value = new Date();
    pending.value = sortByStaleness(
      pickDomainBPending(res.data ?? []),
      now.value
    );
  } catch {
    pending.value = [];
  }
}

/** 展示条数（域 B 待处理） */
const count = computed(() => pending.value.length);

/** 最久未处理的那条已挂多少天（标题里点出来的那一条） */
const stalestDays = computed(() => {
  if (!pending.value.length) return null;
  return pendingDays(pending.value[0].first_detected_at, now.value);
});

/** 收起态最多展示几条 */
const visibleItems = computed(() =>
  expanded.value ? pending.value : pending.value.slice(0, COLLAPSED_LIMIT)
);
const hiddenCount = computed(() =>
  expanded.value ? 0 : Math.max(0, pending.value.length - COLLAPSED_LIMIT)
);

/** 当前路由是否该展示（工作台页自带提醒，不重复） */
const routeAllowed = computed(() => shouldShowOnRoute(route.name as string));

/** 去对账工作台域 B 处理：横幅上的数字与落地后的「待裁决差异」一致 */
function goToWorkbench(): void {
  router.push({
    path: "/investment/reconcile-workbench",
    query: { domain: "B" }
  });
}

onMounted(async () => {
  const familyId = await resolveFamilyId();
  if (isDismissed(familyId)) {
    loading.value = false;
    return;
  }
  await loadPending();
  loading.value = false;
});

/**
 * 从工作台返回时重新取数。
 *
 * 为什么需要：本组件挂在**布局**上（布局常驻、路由切换不重挂载），`onMounted`
 * 只在首次进入应用时跑一次。若不刷新，用户在工作台处理完差异再返回其它页面，
 * 横幅仍显示处理前的条数——一个会撒谎的提醒比没有提醒更糟。
 *
 * 只在「上一个路由是工作台」时刷新：其它导航不重复打接口。
 */
watch(
  () => route.name,
  (next, prev) => {
    if (prev === WORKBENCH_ROUTE_NAME && !dismissed.value) {
      void loadPending();
    }
  }
);
</script>

<template>
  <div
    v-if="routeAllowed && !loading && !dismissed && count > 0"
    class="recon-banner"
    role="alert"
  >
    <div class="recon-banner__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
        <path
          d="M12 4.5L21 19.5H3L12 4.5Z"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linejoin="round"
        />
        <path
          d="M12 10v4"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
        />
        <circle cx="12" cy="16.6" r="1" fill="currentColor" />
      </svg>
    </div>

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

      <ul class="recon-banner__list">
        <li
          v-for="item in visibleItems"
          :key="item.id"
          class="recon-banner__item"
        >
          <span class="recon-banner__symbol">{{ item.symbol }}</span>
          <span class="recon-banner__meta">
            {{ discrepancyTypeLabel(item.discrepancy_type) }}差异
            <template v-if="item.diff !== null">
              · 差额 {{ formatDiff(item.diff) }}</template
            >
          </span>
          <span class="recon-banner__age">
            {{ ageLabel(pendingDays(item.first_detected_at, now)) }}
          </span>
        </li>
      </ul>

      <div class="recon-banner__actions">
        <button
          type="button"
          class="recon-banner__primary"
          @click="goToWorkbench"
        >
          去对账工作台处理
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
        差异意味着账上的数量或成本与流水推演对不上，可能影响持仓市值与收益。请到对账工作台核对处理。
      </p>
    </div>

    <button
      type="button"
      class="recon-banner__close"
      title="本次会话不再提示（刷新后恢复）"
      aria-label="本次会话不再提示"
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
/*
  语义色：pending 差异是「需关注」而非「错误」，故取 warning 色族而非 danger。
  --color-warning 仅作底色/边框（白底仅 1.68:1，不可作前景），文字走
  --color-warning-ink（白底 5.71:1）。
*/
.recon-banner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  margin-bottom: 16px;
  color: var(--text-primary);
  background: var(--color-warning-20);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm, 8px);
}

.recon-banner__icon {
  flex: none;
  margin-top: 2px;
  color: var(--color-warning-ink);
}

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

.recon-banner__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.recon-banner__item {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
}

.recon-banner__symbol {
  font-weight: 600;
  color: var(--text-primary);
}

.recon-banner__meta,
.recon-banner__age {
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

.recon-banner__close {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: background-color 0.15s ease;
}

.recon-banner__close:hover {
  background: var(--color-warning-20);
}
</style>
