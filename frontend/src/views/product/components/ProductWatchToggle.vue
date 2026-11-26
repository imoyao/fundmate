<!--
  ProductWatchToggle · 产品详情页页头的「自选」控件（2026-11-26）

  ## 为什么要有它

  用户实测：「没办法取消自选，没办法显示 tag，我不知道它的意义是什么。」
  在此之前，自选状态只以识别卡里一行死文字（「自选 / 已关注」）出现：不可点、
  不说属于哪个分组、打了什么标签。识别卡本轮已按「身份事实才成卡」收窄
  （组合 / 经理类整卡不渲染，见 `productIdentityFacts.ts`），于是**自选这件事
  必须有自己的、可操作的落点**——就是页头这个控件。

  放在页头 `#action` 槽而不是正文：它是**页面级操作**，且状态（已关注 / 未关注）
  是「我和标的关系」，属于「一层页头」承担的内容（design.md · 页头操作槽）。

  ## 三个状态，不是两个

  `in_watchlist` 来自 resolve 这个**可选登录**端点：`null` = 未登录（未知），
  与 `false`（确定没关注）是两件事。未知时整个控件**不渲染**——宁可没有入口，
  也不要抛给未登录用户一个点下去必然 401 的按钮。

  ## 已关注为什么还要再查一次

  resolve 只回一个布尔，回答不了「在哪个分组、打了什么标签」。故 `true` 时补一次
  `GET /watchlist/items/?symbol=`（`per_page=1`，不拉整页）。这条请求失败时按钮
  仍显示「已关注」（那是 resolve 的事实），但面板里**不给**「取消自选」：没有
  item id 就删不掉，与其点了报错，不如说清「去自选页管理」。

  ## 取消为什么分两种走法

  有分组 / 标签时必须先确认：删掉自选项会**一并解除**这些归类，而归类是用户
  手工打的，重建自选不会自动恢复。没有归类时直接删——它只是一个代码，
  加回来零成本。判据是 `needsConfirm`，不是「一律确认」也不是「一律不确认」。
-->
<template>
  <div v-if="state !== 'unknown'" class="watch-toggle">
    <!-- 已关注：按钮本身说「你说过要关注它」，点开才是细节与操作 -->
    <el-popover
      v-if="state === 'on'"
      v-model:visible="panelOpen"
      placement="bottom-end"
      :width="272"
      trigger="click"
      popper-class="watch-toggle__popper"
    >
      <template #reference>
        <el-button
          ref="btnRef"
          size="small"
          text
          class="watch-toggle__btn"
          :style="{ color: 'var(--brand-ink)' }"
          aria-haspopup="dialog"
          :aria-expanded="panelOpen"
        >
          <IconifyIconOffline icon="ep:star-filled" class="mr-1" />
          已关注<span v-if="groupHint" class="watch-toggle__hint">
            · {{ groupHint }}</span
          >
        </el-button>
      </template>

      <div class="watch-panel">
        <div class="watch-panel__row">
          <span class="watch-panel__label">分组</span>
          <span v-if="!groupNames.length" class="watch-panel__empty">
            未分组
          </span>
          <span
            v-for="name in groupNames"
            :key="name"
            class="watch-panel__chip"
            >{{ name }}</span
          >
        </div>
        <div class="watch-panel__row">
          <span class="watch-panel__label">标签</span>
          <span v-if="!tagNames.length" class="watch-panel__empty">
            {{ tagFallback }}
          </span>
          <span v-for="name in tagNames" :key="name" class="watch-panel__chip">
            {{ name }}
          </span>
        </div>
        <div class="watch-panel__foot">
          <button type="button" class="watch-panel__link" @click="goManage">
            在自选中管理
          </button>
          <!-- 没有 item id 时不提供删除：不知道删谁，点了只能报错 -->
          <button
            v-if="item?.id"
            type="button"
            class="watch-panel__remove"
            :disabled="removing"
            @click="remove"
          >
            取消自选
          </button>
        </div>
      </div>
    </el-popover>

    <!-- 未关注：一次点击进「添加自选」弹窗（已预填本产品），顺手就能选分组 / 标签 -->
    <el-button
      v-else
      size="small"
      text
      class="watch-toggle__btn"
      :style="{ color: 'var(--text-secondary)' }"
      :loading="loading"
      @click="addOpen = true"
    >
      <IconifyIconOffline icon="ep:star" class="mr-1" />
      自选
    </el-button>

    <AddToWatchlistModal
      v-model="addOpen"
      :initial-asset="addAsset"
      @submitted="onAdded"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import type { SearchAssetOption } from "@/components/QuickEntry/assetOptionColumns";
import {
  deleteWatchlistItem,
  getWatchlistItems,
  getWatchlistTags
} from "@/api/watchlist";
import type { WatchlistItem, WatchlistTag } from "@/api/watchlist";

const props = defineProps<{
  symbol: string;
  displayName: string;
  market?: string | null;
  assetType?: string | null;
  venue?: string | null;
  /** resolve 的 `in_watchlist`：**null = 未登录 / 未知**，不渲染控件 */
  inWatchlist: boolean | null;
}>();

const router = useRouter();

/** unknown / off / on —— 见头注释「三个状态，不是两个」 */
const state = ref<"unknown" | "off" | "on">("unknown");
const item = ref<WatchlistItem | null>(null);
const loading = ref(false);
const removing = ref(false);
const panelOpen = ref(false);
const addOpen = ref(false);
const tagCatalog = ref<WatchlistTag[] | null>(null);
const btnRef = ref<{ $el?: HTMLElement } | null>(null);

/** 预填给「添加自选」弹窗的资产（产品已确定，不该让用户再搜一遍） */
const addAsset = computed<SearchAssetOption>(() => ({
  symbol: props.symbol,
  name: props.displayName,
  market: props.market ?? "",
  type: props.assetType ?? undefined,
  venue: props.venue ?? ""
}));

const groupNames = computed(() => item.value?.group_names ?? []);

/** 按钮上只放**一个**分组名做提示，多了会撑爆页头；完整列表在面板里 */
const groupHint = computed(() => {
  const names = groupNames.value;
  if (!names.length) return "";
  return names.length > 1 ? `${names[0]} +${names.length - 1}` : names[0];
});

const tagNames = computed(() => {
  const ids = item.value?.tag_ids ?? [];
  if (!ids.length) return [];
  const catalog = tagCatalog.value ?? [];
  const byId = new Map(catalog.map(t => [t.id, t.name]));
  return ids
    .map(id => byId.get(id))
    .filter((name): name is string => Boolean(name));
});

/** 有标签 id 但目录还没回来（或拉失败）时，不能谎称「未打标签」 */
const tagFallback = computed(() =>
  (item.value?.tag_ids?.length ?? 0) > 0 ? "…" : "未打标签"
);

const needsConfirm = computed(() => {
  const it = item.value;
  if (!it) return false;
  return (it.group_ids?.length ?? 0) > 0 || (it.tag_ids?.length ?? 0) > 0;
});

async function loadTags() {
  try {
    const res = await getWatchlistTags();
    tagCatalog.value = res.data ?? [];
  } catch {
    // 拉不到标签目录时保留 null：`tagFallback` 会显示「…」而不是「未打标签」
    tagCatalog.value = null;
  }
}

async function loadItem() {
  const symbol = props.symbol;
  loading.value = true;
  try {
    // per_page=1：只想知道「是哪一条自选项」，不拉整页富化数据
    const res = await getWatchlistItems({ symbol, per_page: 1 });
    if (symbol !== props.symbol) return; // 慢响应：产品已切走
    item.value = (res.data ?? [])[0] ?? null;
    if (item.value?.tag_ids?.length) void loadTags();
  } catch {
    if (symbol === props.symbol) item.value = null;
  } finally {
    if (symbol === props.symbol) loading.value = false;
  }
}

function sync() {
  panelOpen.value = false;
  item.value = null;
  tagCatalog.value = null;
  if (props.inWatchlist == null) {
    state.value = "unknown";
    return;
  }
  state.value = props.inWatchlist ? "on" : "off";
  if (props.inWatchlist) void loadItem();
}

watch(() => [props.symbol, props.inWatchlist], sync, { immediate: true });

function onAdded() {
  addOpen.value = false;
  state.value = "on";
  void loadItem();
}

function goManage() {
  panelOpen.value = false;
  // 自选页路由是 `/watchlist`（`/asset/watchlist` 不存在，会被本页路由抢先匹配）
  router.push("/watchlist");
}

async function remove() {
  const it = item.value;
  if (!it?.id) return;
  if (needsConfirm.value) {
    try {
      await ElMessageBox.confirm(
        "取消后，它所在的分组与标签会一并解除，重新自选也不会自动恢复。",
        "取消自选？",
        {
          type: "warning",
          confirmButtonText: "取消自选",
          cancelButtonText: "保留"
        }
      );
    } catch {
      return;
    }
  }
  removing.value = true;
  try {
    await deleteWatchlistItem(it.id);
    state.value = "off";
    item.value = null;
    panelOpen.value = false;
    ElMessage.success("已取消自选");
  } catch {
    ElMessage.error("取消自选失败，请稍后重试");
  } finally {
    removing.value = false;
  }
}

/** Esc 关闭面板并把焦点还给按钮（el-popover 不处理键盘） */
function onKeydown(e: KeyboardEvent) {
  if (e.key !== "Escape" || !panelOpen.value) return;
  panelOpen.value = false;
  btnRef.value?.$el?.focus();
}

onMounted(() => document.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => document.removeEventListener("keydown", onKeydown));
</script>

<style scoped>
.watch-toggle {
  display: inline-flex;
  align-items: center;
}

/* 分组名提示：页头宽度有限，超长省略，完整值仍在面板里 */
.watch-toggle__hint {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.watch-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.watch-panel__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  align-items: center;
}

.watch-panel__label {
  flex: none;
  width: 32px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.watch-panel__empty {
  font-size: var(--text-small);
  color: var(--text-tertiary);
}

.watch-panel__chip {
  padding: 1px 8px;
  font-size: var(--text-label);
  color: var(--text-primary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.watch-panel__foot {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  margin-top: var(--space-1);
  border-top: 1px solid var(--border-subtle);
}

.watch-panel__link,
.watch-panel__remove {
  padding: 0;
  font-size: var(--text-small);
  cursor: pointer;
  background: none;
  border: 0;
}

.watch-panel__link {
  color: var(--color-primary-ink);
}

.watch-panel__link:hover {
  text-decoration: underline;
}

.watch-panel__remove {
  color: var(--color-danger-ink);
}

.watch-panel__remove:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
