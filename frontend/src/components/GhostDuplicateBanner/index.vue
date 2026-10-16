<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  listGhostDuplicates,
  type GhostDuplicateGroupItem
} from "@/api/reconciliation";
import { getMe } from "@/api/auth";
import { formatDate } from "@/utils/date";
import { txnTypeLabel } from "@/constants";

const router = useRouter();

const groups = ref<GhostDuplicateGroupItem[]>([]);
const ignoredCount = ref(0);
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

/**
 * 关闭语义：**本次会话忽略**，不是「永久关闭」。
 *
 * 原实现是单一永久 key，且 `onMounted` 命中后连请求都不发 —— 于是「关掉一次」
 * 等于「这条告警从此不存在」，换家庭还共用同一个开关（语义错误）。
 * 现在告警有了真正的落点（对账工作台域 D），关闭只是「这次先不看」：
 * 刷新/重进页面即恢复检查，不写持久层。
 *
 * 用 `sessionStorage` 而非组件内 `ref`：多标签页之间共享一次会话的「我已看过」意图，
 * 关掉浏览器即清空，不跨会话残留（也就不需要用户去「重新打开」某个开关）。
 */
const STORAGE_KEY = "ghost_dup_banner_dismissed";

/** 本次会话是否已关闭（sessionStorage，key 带 family_id）。 */
function isDismissed(familyId: number | null): boolean {
  try {
    return sessionStorage.getItem(dismissKey(familyId)) === "1";
  } catch {
    return false;
  }
}

/**
 * 按家庭隔离的 dismiss key。
 *
 * 卡面验收「localStorage key 必须带 family_id」——此前是单一常量 key，
 * 换家庭 / 换账号共用同一开关。家庭 id 来自 `GET /api/auth/me/`（`data.family.id`），
 * 前端没有更轻的同步来源（路由守卫只把展示名写进 localStorage，不含 family）。
 * 拿不到 family 时退化为无后缀 key：宁可「隔离失效」也不要「开关失效」——
 * 后者会让用户在拿不到 /me 的异常态下被一条关不掉的横幅一直顶着。
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

/** 去对账工作台域 D 处理（#2151）：跳转带上 `?domain=D`，工作台按 query 落地该域 */
function goToWorkbench(): void {
  router.push({
    path: "/investment/reconcile-workbench",
    query: { domain: "D" }
  });
}

onMounted(async () => {
  const familyId = await resolveFamilyId();
  if (isDismissed(familyId)) {
    loading.value = false;
    return;
  }
  try {
    // 换用 reconciliation 域的列表端点（而非 summary 域的幽灵扫描）：
    // ① 只有它返回 `fingerprint` 与组内明细，是「去处理」的定位键；
    // ② 只有它**已减掉忽略项**——否则横幅报「407 组」而域 D 只剩 401 组，
    //    用户点过去第一眼就是数字对不上（issue 明确要避免的「新的困惑」）。
    const res = await listGhostDuplicates();
    groups.value = res.data?.groups ?? [];
    ignoredCount.value = res.data?.ignored_count ?? 0;
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
           #2151 起后端有 ignore 接口、工作台也有域 D，故这里给出真实的处置出口：
           「去处理」跳域 D 逐组核对（忽略可撤销），不再是死路。 -->
      <div class="ghost-dup-banner__actions">
        <button
          type="button"
          class="ghost-dup-banner__primary"
          @click="goToWorkbench"
        >
          去对账工作台处理
        </button>
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
        重复记录（保留你认为真实的那一笔，另一份删除）。
      </p>
      <p v-if="ignoredCount > 0" class="ghost-dup-banner__ignored">
        另有 {{ ignoredCount }} 组已忽略，可在对账工作台域 D 撤销。
      </p>
    </div>

    <button
      type="button"
      class="ghost-dup-banner__close"
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
  gap: 12px;
  align-items: center;
  margin-top: 8px;
}

/* 主行动（去处理）：与「展开/收起」这类次级链接区分开，是横幅真正的出口 */
.ghost-dup-banner__primary {
  padding: 4px 12px;
  font-size: var(--text-label, 13px);
  font-weight: 600;
  color: var(--text-inverse);
  cursor: pointer;

  /* 实底主按钮：底色走 --brand-solid、文字配 --text-inverse（#1600 约定的唯一组合）。
     原先想用 --color-rise-ink，但它是「涨」语义的**文字级**令牌，借来当按钮底色
     既是语义误用，也把「告警」染成「涨」的色相。 */
  background: var(--brand-solid);
  border: none;
  border-radius: var(--radius-sm, 8px);
  transition: opacity 0.15s ease;
}

.ghost-dup-banner__primary:hover {
  opacity: 0.88;
}

.ghost-dup-banner__ignored {
  margin: 4px 0 0;
  font-size: var(--text-label, 13px);
  color: var(--color-rise-ink);
  opacity: 0.75;
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
