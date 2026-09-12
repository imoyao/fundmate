<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups/tags/toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistToolbar 同模式） */
import {
  computed,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick
} from "vue";
import { Files, Filter, Folder, Plus } from "@element-plus/icons-vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import type { WatchlistTag } from "@/api/watchlist";
import { DEFAULT_TAG_COLOR } from "@/constants/watchlist";
import { assetTypeLabel } from "@/composables/useEnumLabels";

/**
 * 自选筛选条（分组胶囊 Tab + 标签筛选 + 视图 Segmented），从 index.vue 顶部区块抽出（2026-08-20）。
 * 2026-08-21 重构：分组 Tab 与标签筛选 / 视图 segmented 合并为单行三段式
 * （左固定筛选 + 中段 tab 横向滚动 + 右固定「+」），与 design.md 分组胶囊 Tab
 * 「tab 左对齐 + 右侧 segmented」布局规范一致（规范 414），省去独立筛选行。
 * 2026-09-05 修订：原 #actions 快捷图标组（刷新/导出/AI导入/实时估值）上移至
 * index.vue 第一行 .head-primary，本行收窄为纯筛选职责，不再拥挤。
 * 纯展示 + 事件转发：状态全部在 groups / tags / toolbar 三个 composable，本组件不持有业务状态。
 */
const props = defineProps<{
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: WatchlistToolbarState;
  onRefresh: () => void;
}>();

const emit = defineEmits<{
  (e: "view-change"): void;
  /**
   * 「筛选」面板确定：类型 + 标签两组草稿均已提交，请父页面按新条件刷新列表。
   * 仅在「标签未变化、只有类型变化」时触发——标签变化由 useWatchlistData 的
   * watch(selectedFilterTagIds) 自动置第 1 页并刷新，两者同时触发会打两次请求。
   */
  (e: "filter-apply"): void;
  /** 管理分组本身（新建/改名/删除）→ GroupManagerDialog */
  (e: "manage-groups"): void;
  /** #987：管理当前自定义分组「里有哪些产品」→ GroupItemsDialog */
  (e: "manage-group-items"): void;
}>();

// 状态注入模式：groups / tags / toolbar 为 composable 实例 prop，
// 双向绑定经 computed get/set 桥接其内部 ref（避免 vue/no-mutating-props）
const activeGroupModel = computed({
  get: () => props.groups.activeGroup.value,
  set: (value: string) => {
    props.groups.activeGroup.value = value;
  }
});
const allGroups = computed(() => props.groups.allGroups.value);
const tagFilterVisibleModel = computed({
  get: () => props.tags.tagFilterVisible.value,
  set: (value: boolean) => {
    props.tags.tagFilterVisible.value = value;
  }
});
const draftFilterTagIdsModel = computed({
  get: () => props.tags.draftFilterTagIds.value,
  set: (value: number[]) => {
    props.tags.draftFilterTagIds.value = value;
  }
});
const allTags = computed(() => props.tags.allTags.value);
const selectedTagCount = computed(
  () => props.tags.selectedFilterTagIds.value.length
);

// ── 类型筛选（2026-09-09 用户拍板方案 A；2026-09-12 改为「主界面单选快捷 + 弹层多选」）──
// 主界面「类型快捷 segmented」（全部/股票/基金/ETF/可转债）为单维度快速切换（单选覆盖式）；
// 「筛选」弹层内「产品类型」为弹层多选，可与标签正交组合（如「股票 + 某标签」）。
// venue（场内/场外）维度 2026-09-12 已从主界面移除：普通用户对场内/场外心智门槛高，
// 且与类型维度重叠；当前 toolbar.currentView 恒为 'all'，后端不过滤 venue（见 useWatchlistData）。
// 类型 key 列表为自选场景交易性类型（业务选择属前端职责）；中文标签统一走
// useEnumLabels.assetTypeLabel（后端 /enums/asset_type 唯一真相源，禁止手抄映射）。
const ASSET_TYPE_OPTIONS = [
  "stock",
  "etf",
  "fund",
  "money_fund",
  "bond",
  "index",
  "crypto",
  "reverse_repo",
  // #1285 品类视图：经理 / 投顾组合也需可筛选（此前缺失 → 无法进入其品类视图）
  "manager",
  "portfolio"
] as const;

/** 持仓分组（activeGroup === 'holding'）下可筛选的资产类型：仅股票与基金。
 *  经理 / 组合 / 指数 / ETF / 可转债等在「持仓」语义下不存在（持仓只来自 positions 表，
 *  其 asset_type 实际为 stock/fund 类），禁止选择，从根上杜绝
 *  「持仓分组筛经理却显示股票、表头却变」的 bug（用户反馈，问题 2）。 */
const HOLDING_ALLOWED_TYPES = ["stock", "fund"] as const;

const selectedAssetTypesModel = computed({
  get: () => props.toolbar.selectedAssetTypes.value,
  set: (value: string[]) => {
    props.toolbar.selectedAssetTypes.value = value;
  }
});

// ── 持仓分组限制（问题 2 修复）──
// 当前是否在「持仓」分组：持仓分组只有真实持仓（股票 / 基金类），
// 经理 / 组合 / 指数等无持仓语义的类型在此视图下不可选。
const isHoldingGroup = computed(
  () => props.groups.activeGroup.value === "holding"
);
// 弹层内展示的类型选项：持仓分组下收窄为仅股票 / 基金，避免误选无持仓语义的类型。
const visibleTypeOptions = computed<string[]>(() =>
  isHoldingGroup.value ? [...HOLDING_ALLOWED_TYPES] : [...ASSET_TYPE_OPTIONS]
);

// Popover 内当前激活的分类面板：产品类型 / 资产标签
const activePanel = ref<"type" | "tag">("type");

// 主界面高频类型快捷入口：全部 / 股票 / 基金 / ETF / 可转债（单选覆盖式）。
// 与「筛选」Popover 的多选正交：此处是单维度快速切换，组合筛选仍走 Popover。
// 中文 label 走 assetTypeLabel（后端 /enums/asset_type 唯一真相源，禁止手抄映射），
// 「可转债」对应资产类型 bond（useEnumLabels 已映射）。
const QUICK_TYPES = [
  { label: assetTypeLabel("stock"), value: "stock" },
  { label: assetTypeLabel("fund"), value: "fund" },
  { label: assetTypeLabel("etf"), value: "etf" },
  { label: assetTypeLabel("bond"), value: "bond" }
] as const;

// segmented 选项含「全部」（清除类型筛选），其余为高频类型。
const TYPE_SEGMENTED_OPTIONS = [
  { label: "全部", value: "all" },
  ...QUICK_TYPES
] as const;

/**
 * 当前单选激活项派生：
 * - 无类型筛选 → 'all'（高亮「全部」）；
 * - 恰好单选一个高频类型 → 该类型；
 * - 多选 / 选了 Popover 里的其它类型 → ''（无高亮，组合态，看「筛选」角标）。
 */
const quickActive = computed<string>(() => {
  const t = selectedAssetTypesModel.value;
  if (t.length === 0) return "all";
  if (t.length === 1 && QUICK_TYPES.some(q => q.value === t[0])) return t[0];
  return "";
});

/**
 * 主界面类型快捷入口（单选覆盖式）：点击即设置该类型为唯一生效筛选并刷新列表；
 * 再次点击当前项 → 取消回「全部」；「全部」→ 清空类型筛选。
 * 与 Popover 内多选正交：此处只能单维度，复杂组合进 Popover。
 */
function selectQuickType(value: string) {
  if (value === "all") {
    if (selectedAssetTypesModel.value.length === 0) return;
    selectedAssetTypesModel.value = [];
  } else if (
    selectedAssetTypesModel.value.length === 1 &&
    selectedAssetTypesModel.value[0] === value
  ) {
    selectedAssetTypesModel.value = [];
  } else {
    selectedAssetTypesModel.value = [value];
  }
  draftAssetTypes.value = [...selectedAssetTypesModel.value];
  emit("filter-apply");
}

// 标签过多时面板内搜索（标签会随使用无限增长，见用户反馈）。
const tagSearch = ref("");
const filteredTags = computed(() => {
  const kw = tagSearch.value.trim().toLowerCase();
  if (!kw) return allTags.value;
  return allTags.value.filter(t => t.name.toLowerCase().includes(kw));
});

// 类型草稿。与标签草稿同一节奏：打开「筛选」面板时同步已生效筛选，点「确定」才提交。
// 面板开合统一由 tagFilterVisibleModel 承担（类型与标签本就是同一个面板，见下方 watch）。
const draftAssetTypes = ref<string[]>([]);

function toggleDraftType(type: string) {
  const idx = draftAssetTypes.value.indexOf(type);
  if (idx >= 0) draftAssetTypes.value.splice(idx, 1);
  else draftAssetTypes.value.push(type);
}

/** 已生效的筛选条件数（类型 + 标签）：用于筛选入口按钮的角标 */
const activeFilterCount = computed(
  () => selectedAssetTypesModel.value.length + selectedTagCount.value
);

/** Popover 内草稿状态的已选计数：用于底部操作栏实时反馈 */
const draftFilterCount = computed(
  () => draftAssetTypes.value.length + draftFilterTagIdsModel.value.length
);

/** 是否有「已生效」或「草稿中」的条件：决定面板内「重置」是否可用 */
const hasAnyFilter = computed(
  () =>
    activeFilterCount.value > 0 ||
    draftAssetTypes.value.length > 0 ||
    draftFilterTagIdsModel.value.length > 0
);

// 打开「筛选」面板时把已生效筛选同步到两组草稿（类型 + 标签）。
// 原触发按钮 @click 内的 onTagFilterShow 迁移至此：trigger="click" 后开合由 EP 接管，
// 组件不再经手打开动作。
watch(tagFilterVisibleModel, visible => {
  if (!visible) return;
  activePanel.value = "type";
  props.tags.onTagFilterShow();
  draftAssetTypes.value = [...selectedAssetTypesModel.value];
});

const addDialogVisible = ref(false);

// ── 分组区横向滚动手势（2026-09-05）──
// 分组多时滚动条若常驻占位，会把分组区撑得比右侧操作区高几像素，造成两侧中心错位
// （用户反馈：滚动条出现时两边对不上）。故隐藏原生滚动条、改用「滚轮/触控板横滑」，
// 右缘渐变遮罩（.group-tabs-fade）负责提示还有更多，行高恒定、与右侧恒对齐。
const groupScrollEl = ref<HTMLElement>();
/** 右缘渐变遮罩是否显示：仅当分组 tab 横向溢出时才出现，避免未溢出时误导用户（#ai-review-inline） */
const showGroupFade = ref(false);
function updateGroupFade() {
  const el = groupScrollEl.value;
  showGroupFade.value = !!el && el.scrollWidth > el.clientWidth + 1;
}

/** 滚轮横滑：仅当分组区确有溢出时拦截纵向滚轮转为横向，避免干扰行内其它滚动。
 *  绑定在模板 @wheel 上（Vue 自动随 batchMode v-if 切换挂载/解绑）。 */
function handleGroupWheel(e: WheelEvent) {
  const el = groupScrollEl.value;
  if (!el || el.scrollWidth <= el.clientWidth + 1) return;
  const delta = e.deltaY || e.deltaX;
  const next = el.scrollLeft + delta;
  // 仅在滚动位置确实会变化时才拦截纵向滚轮，避免到达边缘时阻止页面竖向滚动
  if (next < 0 || next > el.scrollWidth - el.clientWidth) return;
  e.preventDefault();
  el.scrollLeft = next;
}

// 标签筛选胶囊：点击切换草稿选中态（与「管理标签」的颜色胶囊同语言）
function toggleDraftTag(id: number) {
  const idx = draftFilterTagIdsModel.value.indexOf(id);
  if (idx >= 0) draftFilterTagIdsModel.value.splice(idx, 1);
  else draftFilterTagIdsModel.value.push(id);
}

/**
 * 「确定」：一次性提交类型 + 标签两组草稿并关闭面板。
 *
 * 刷新只走**一条**路径，避免重复请求：
 * - 标签有变化 → useWatchlistData 内部 `watch(selectedFilterTagIds)` 会自动置第 1 页并刷新
 *   （类型已先写入，刷出来的就是新条件）；
 * - 只有类型变化 → 标签 watch 不触发，补发 `filter-apply` 让页面刷新；
 * - 两者都没变 → 只关面板，不打请求。
 */
function applyFilters() {
  const beforeTags = [...props.tags.selectedFilterTagIds.value]
    .sort()
    .join(",");
  const beforeTypes = [...selectedAssetTypesModel.value].sort().join(",");

  selectedAssetTypesModel.value = [...draftAssetTypes.value];
  props.tags.selectedFilterTagIds.value = [...draftFilterTagIdsModel.value];
  tagFilterVisibleModel.value = false;

  const tagsChanged =
    [...props.tags.selectedFilterTagIds.value].sort().join(",") !== beforeTags;
  const typesChanged =
    [...selectedAssetTypesModel.value].sort().join(",") !== beforeTypes;
  if (!tagsChanged && typesChanged) emit("filter-apply");
}

/** 一键重置：清空两组草稿后走同一条提交路径（清空即清除筛选），并关闭面板 */
function resetAllFilters() {
  draftAssetTypes.value = [];
  draftFilterTagIdsModel.value = [];
  applyFilters();
}

/**
 * 标签胶囊颜色：未选中时保留独立色点；选中态要求「圆点与背景融为一体」，
 * 因此用标签色作为实底、文字反白，视觉上即为一个有色实心胶囊（不再显示前缀圆点）。
 */
function chipStyle(tag: WatchlistTag) {
  const c = tag.color || DEFAULT_TAG_COLOR;
  return {
    "--chip-color": "white",
    "--chip-bg": c,
    "--chip-border": c
  } as Record<string, string>;
}

// 渐变遮罩按需显示：分组 tab 溢出时才出现，否则隐藏（#ai-review-inline）。
// ResizeObserver 覆盖窗口/容器尺寸变化；watch 分组数量变化覆盖增删分组导致的溢出变化。
let groupFadeObserver: ResizeObserver | undefined;
onMounted(() => {
  const el = groupScrollEl.value;
  if (!el) return;
  updateGroupFade();
  groupFadeObserver = new ResizeObserver(updateGroupFade);
  groupFadeObserver.observe(el);
});
onBeforeUnmount(() => groupFadeObserver?.disconnect());
watch(
  () => allGroups.value.length,
  () => nextTick(updateGroupFade)
);
</script>

<template>
  <div class="filter-bar">
    <!-- 筛选行（双行分区布局的「第二行」，见 index.vue head-primary 注释）：
         分组 Tab（主导航，弹性横向滚动，永远最左）
         + 次级操作（新建分组 / 管理分组 / 标签筛选 / 视图 segmented）
         （#actions 快捷图标组已于 2026-09-05 上移第一行 head-primary，本行保持纯筛选）

         批量模式（batchMode）：分组与筛选整体隐藏（批量工具条占用第一行），
         避免表格上方出现两排状态不同的操作。 -->
    <div v-if="!toolbar.batchMode.value" class="filter-row">
      <!-- 左段（弹性）：分组胶囊 Tab（design.md「分组胶囊 Tab · 方案 B」，水平滑动、数量徽章 tabular-nums）。
           自定义分组多时会横向滚动，右缘用渐变遮罩暗示「右侧还有」（2026-09-05）。
           注意：此处不要套裸 <template>（无 v-if/v-for/v-slot 指令），否则会被渲染成原生
           <template> 元素，其 children 进入惰性 .content 片段而不显示到页面（已踩坑）。 -->
      <div class="group-tabs-wrap">
        <div
          ref="groupScrollEl"
          class="group-tabs-scroll"
          @wheel="handleGroupWheel"
        >
          <button
            v-for="g in allGroups"
            :key="g.key"
            type="button"
            class="group-tab"
            :class="{ 'is-active': g.key === activeGroupModel }"
            :title="g.label"
            @click="activeGroupModel = g.key"
          >
            <!-- 分组色点：用户数据色（非设计令牌），缺失回退中性 token（数据色例外） -->
            <span
              v-if="g.color"
              class="group-tab-dot"
              :style="{ backgroundColor: g.color }"
            />
            <span class="group-tab-label">{{ g.label }}</span>
            <span
              v-if="g.count > 0"
              class="group-tab-count"
              :style="{
                /* 分组/标签色为用户数据（非设计令牌），缺失回退中性 token（数据色例外） */
                color: g.color ? g.color : undefined
              }"
            >
              {{ g.count }}
            </span>
          </button>
        </div>
        <!-- 右缘渐变遮罩：分组溢出时暗示可横向滑动（纯装饰，不拦截指针事件） -->
        <span class="group-tabs-fade" aria-hidden="true" />
      </div>

      <!-- 右段（固定）：分组操作 + 视图筛选 + 高频类型快捷 + 复杂筛选入口，
           不随分组 tab 滚动 -->
      <div class="filter-bar__right">
        <!-- 新建分组「+」+ 管理分组「📁」：固定展示，避免分组过多时被挤进滚动区 -->
        <el-button
          class="group-tab-add"
          circle
          aria-label="新建分组"
          @click="addDialogVisible = true"
        >
          <el-icon><Plus /></el-icon>
        </el-button>
        <el-tooltip content="管理分组" placement="bottom">
          <el-button
            class="manage-groups-btn"
            circle
            aria-label="管理分组"
            @click="emit('manage-groups')"
          >
            <el-icon><Folder /></el-icon>
          </el-button>
        </el-tooltip>
        <!-- 「管理本组产品」：仅当前选中自定义分组时出现（issue #987）。
             与上方「管理分组」（管分组本身的新建/改名/删除）是两件事——本入口
             管「这个组里有哪些产品」，系统分组由后端规律维护故不展示。 -->
        <el-tooltip
          v-if="groups.currentIsCustom"
          content="管理本组产品"
          placement="bottom"
        >
          <el-button
            class="manage-group-items-btn"
            circle
            aria-label="管理本组产品"
            @click="emit('manage-group-items')"
          >
            <el-icon><Files /></el-icon>
          </el-button>
        </el-tooltip>
        <div class="right-divider" />

        <!-- 类型快捷 segmented：全部 / 股票 / 基金 / ETF / 可转债（单选覆盖式）。
             手写分段控制器（弃用 el-segmented：JS 绝对定位滑块与自定义尺寸错位，
             见 OcrImportModal 同款决策）；选中态仅浅红底 + 深红字。
             与「筛选」Popover 多选正交：此处单维度快速切换，组合仍走 Popover。 -->
        <div class="type-segmented" role="tablist" aria-label="类型快捷筛选">
          <button
            v-for="opt in TYPE_SEGMENTED_OPTIONS"
            :key="opt.value"
            type="button"
            role="tab"
            class="type-segmented__item"
            :class="{ 'is-active': quickActive === opt.value }"
            :aria-selected="quickActive === opt.value"
            @click="selectQuickType(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>

        <!-- 复杂筛选入口：合并「类型 / 标签」多选，以 500px 左右分栏 Popover 展示。
             按钮角标表达已生效条件数（0 时不显示）。
             trigger="click" + v-model:visible：EP 原生接管「点击外部 / Esc 自动收起」；
             点外部关闭不丢草稿：草稿仅在重新打开时由 watch 重置为已提交筛选。 -->
        <el-popover
          v-model:visible="tagFilterVisibleModel"
          trigger="click"
          placement="bottom-start"
          :width="500"
          popper-class="watchlist-filter-popper"
        >
          <template #reference>
            <el-button
              class="filter-entry-btn"
              :class="{ 'is-active': activeFilterCount > 0 }"
              aria-label="筛选自选列表"
            >
              <el-icon class="filter-entry-btn__icon"><Filter /></el-icon>
              筛选
              <span v-if="activeFilterCount" class="filter-entry-btn__count">
                {{ activeFilterCount }}
              </span>
            </el-button>
          </template>
          <div class="filter-panel">
            <aside class="filter-panel__sidebar">
              <button
                type="button"
                class="filter-panel__nav"
                :class="{ 'is-active': activePanel === 'type' }"
                @click="activePanel = 'type'"
              >
                <span class="filter-panel__nav-text">产品类型</span>
                <span
                  v-if="draftAssetTypes.length"
                  class="filter-panel__nav-count"
                >
                  {{ draftAssetTypes.length }}
                </span>
              </button>
              <button
                type="button"
                class="filter-panel__nav"
                :class="{ 'is-active': activePanel === 'tag' }"
                @click="activePanel = 'tag'"
              >
                <span class="filter-panel__nav-text">资产标签</span>
                <span
                  v-if="draftFilterTagIdsModel.length"
                  class="filter-panel__nav-count"
                >
                  {{ draftFilterTagIdsModel.length }}
                </span>
              </button>
            </aside>
            <div class="filter-panel__main">
              <div class="filter-panel__body">
                <template v-if="activePanel === 'type'">
                  <section class="filter-panel__section">
                    <div class="filter-panel__chips">
                      <button
                        v-for="t in visibleTypeOptions"
                        :key="t"
                        type="button"
                        class="filter-chip"
                        :class="{
                          'is-selected': draftAssetTypes.includes(t)
                        }"
                        @click="toggleDraftType(t)"
                      >
                        {{ assetTypeLabel(t) }}
                      </button>
                    </div>
                    <p v-if="isHoldingGroup" class="filter-panel__hint">
                      持仓分组仅支持筛选股票 / 基金
                    </p>
                  </section>
                </template>
                <template v-else>
                  <section
                    class="filter-panel__section filter-panel__section--tags"
                  >
                    <el-input
                      v-model="tagSearch"
                      size="small"
                      clearable
                      placeholder="搜索标签"
                      class="filter-panel__search"
                    />
                    <div class="filter-panel__chips">
                      <!-- 标签胶囊：未选中显示标签色点，选中态色点与背景融为一体（实色底 + 白字） -->
                      <button
                        v-for="t in filteredTags"
                        :key="t.id"
                        type="button"
                        class="filter-chip filter-chip--tag"
                        :class="{
                          'is-selected': draftFilterTagIdsModel.includes(t.id)
                        }"
                        :style="chipStyle(t)"
                        @click="toggleDraftTag(t.id)"
                      >
                        <span
                          v-if="!draftFilterTagIdsModel.includes(t.id)"
                          class="filter-chip__prefix"
                        >
                          <span
                            class="filter-chip__dot"
                            :style="{ backgroundColor: t.color || undefined }"
                          />
                        </span>
                        {{ t.name }}
                      </button>
                      <p
                        v-if="filteredTags.length === 0"
                        class="filter-panel__empty"
                      >
                        无匹配标签
                      </p>
                    </div>
                  </section>
                </template>
              </div>

              <!-- 底部固定操作栏：重置 / 已选计数 / 取消 / 确定 永远可见 -->
              <div class="filter-panel__footer">
                <el-button
                  size="small"
                  text
                  type="primary"
                  :disabled="!hasAnyFilter"
                  @click="resetAllFilters"
                >
                  重置
                </el-button>
                <span class="filter-panel__count">
                  已选 {{ draftFilterCount }} 项
                </span>
                <div class="flex gap-2">
                  <el-button
                    size="small"
                    @click="tagFilterVisibleModel = false"
                  >
                    取消
                  </el-button>
                  <!-- 确定：一次性提交「类型 + 标签」两组草稿；刷新只走一条路径，
                       避免标签 watch 与类型刷新叠加成两次请求（见 applyFilters 注释） -->
                  <el-button size="small" type="primary" @click="applyFilters">
                    确定
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </el-popover>
      </div>
    </div>

    <!-- 新建分组弹窗 -->
    <GroupFormDialog v-model="addDialogVisible" @saved="onRefresh" />
  </div>
</template>

<style scoped>
.filter-bar {
  /* design.md「表格/列表/筛选栏：--space-compact(16px)」在卡片外层生效；
     此处为卡内子区块间距，取 12px（--space-3）。
     （2026-09-06 呼吸感回调：曾收紧到 6px 为表格让首屏行数，实测与上方搜索行、
     下方表头三带贴合成一条、分区层级丢失；回到 12px 后筛选带与表格区边界清晰。
     注意：margin 不计入 offsetHeight，故表头吸顶偏移 --watchlist-sticky-top
     仍等于本元素 offsetHeight，吸顶无缝衔接不受本值影响。） */
  margin-bottom: var(--space-3);
}

/* 行布局：分组 tab（弹性滚动）+ 次级操作 + #actions 快捷图标组
   （design.md 分组胶囊 Tab 布局，规范 414）
   flex-wrap: wrap 兜底：窄屏（<1280）放不下时自动换行，宁可高一点也不挤压溢出。 */
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

/* 右段：标签筛选 + 视图 segmented + 新建分组，固定不参与 tab 滚动；
   子项统一 32px 高并垂直居中，保证下拉浮层弹出前后行内元素始终同一条直线 */
.filter-bar__right {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-bar__right > * {
  flex-shrink: 0;
}

/* 右段分隔线：分组操作 与 标签/视图 之间的视觉分隔 */
.right-divider {
  width: 1px;
  height: 20px;
  margin: 0 4px;
  background-color: var(--border-default);
}

.filter-bar__right :deep(.el-popover__reference),
.filter-bar__right :deep(.el-popover) {
  display: inline-flex;
  align-items: center;
}

/* 筛选入口按钮：32px 胶囊，与分组 tab / segmented 同高。
   默认 1px 描边（--border-default）把控件从卡片底色里「立」起来；
   有生效条件时转品牌软底 + 品牌描边 + 数字角标（见 .is-active）。
   关于描边/阴影的取舍（2026-09-11 用户提问）：**只加描边，不加带色阴影**——
   design.md 的阴影是「层级浮起」语义（card / popover / modal），把彩色阴影挂到胶囊上
   属装饰性阴影，与「克制」冲突；描边则是设计语言里既有的构件边界
   （Input / 软按钮 / ProductDisplay 的类型胶囊都在用）。 */
.filter-entry-btn {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.filter-entry-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.filter-entry-btn.is-active {
  font-weight: 500;
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.filter-entry-btn__icon {
  font-size: 14px;
}

/* 条件数角标：品牌实底 + 卡片色字，16px 胶囊（与分组 tab 的数量徽章同为「数字角标」语言） */
.filter-entry-btn__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  color: var(--bg-card);
  background-color: var(--brand-700);
  border-radius: var(--radius-pill);
}

/* ===== 分组胶囊 Tab（design.md「分组胶囊 Tab · 方案 B」2026-08-14，数值与 index.vue 原实现逐值对齐） ===== */

/* 分组区外框：持有 flex 弹性与最小宽度，承载内层滚动区与右缘遮罩。
   min-width 保证分组区不被右侧操作区挤没（#1281 第四轮：本行多了搜索框与按钮组，
   极端窄屏下宁可让整行换行，也要给分组 tab 留 120px 可见区） */
.group-tabs-wrap {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 120px;
}

/* 分组区横滑容器。
   原生滚动条必须隐藏（而非常驻）：WebKit 横向滚动条会在容器底部占约 4px，
   把分组区撑得比右侧操作区高、两侧中心错位（#1281 对齐回归，2026-09-05）。
   横滑能力由模板 @wheel 滚轮手势承担，右缘渐变遮罩提示还有更多。 */
.group-tabs-scroll {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* 旧 Edge/IE */
}

.group-tabs-scroll::-webkit-scrollbar {
  display: none; /* Chrome / Edge（Chromium） */
}

/* 右缘渐变遮罩：自定义分组多、横向可滑动时，用「渐隐到卡片底色」暗示右侧还有内容。
   遮罩固定在可视区右缘（absolute 于 wrap），不随内容滚动；pointer-events:none 不挡点击。 */
.group-tabs-fade {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 28px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, var(--bg-card));
}

/* tab 项：32px 胶囊；选中态软按钮（--brand-100/--brand-700/--brand-400），未选中 --text-secondary + hover --bg-hover */
.group-tab {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.group-tab:hover {
  background-color: var(--bg-hover);
}

.group-tab.is-active {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.group-tab.is-active:hover {
  background-color: var(--brand-200);
}

/* 分组色点：用户数据色常驻可见（数据色例外），选中态软按钮品牌色不受影响 */
.group-tab-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 分组名：展示截断 8 汉字（8em），全名由 title 提示 */
.group-tab-label {
  max-width: 8em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-tab-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.group-tab.is-active .group-tab-count {
  color: var(--brand-700);
}

/* 新建分组按钮：原文字按钮简化为「+」图标（2026-08-21）。
   尺寸规范（2026-09-05）：纯图标按钮统一 28×28，与文字按钮（32）区分层级 */
.group-tab-add {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: 50%;
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.group-tab-add:hover {
  color: var(--text-secondary);
  background-color: var(--bg-hover);
}

/* 管理分组按钮：文件夹图标 = 分组管理语义（非通用齿轮）。
   尺寸规范（2026-09-05）：纯图标按钮统一 28×28 */
.manage-groups-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.manage-groups-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
}

/* 管理本组产品按钮（#987）：与「管理分组」同尺寸同语言（28×28 圆形线框），
   仅图标不同（多文件 = 组内产品清单，文件夹 = 分组本身），避免两个入口混淆 */
.manage-group-items-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.manage-group-items-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
  border-color: var(--brand-400);
}

/* ===== 类型快捷分段控制器（全部/股票/基金/ETF/可转债）：手写，弃用 el-segmented =====
   与分组 tab 同高（轨道 32px）；item 统一几何尺寸，hover/选中仅底色深浅递进，
   文字 flex 居中；选中态仅浅红底 + 深红字，无边框 */
.type-segmented {
  display: flex;
  gap: 2px;
  height: 32px;
  padding: 3px;
  background-color: var(--bg-soft);

  /* 轨道补 1px 描边：与筛选入口按钮、面板内胶囊统一「构件边界」语言，
     避免一整条筛选带里只有分段控制器没有边界、显得糊在卡片底色上（2026-09-11）。
     注意：只在**轨道**上加描边；选中项仍保持「浅红软底 + 深红字、无边框」不变。 */
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

.type-segmented__item {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  padding: 0 14px;
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

/* 原生 button 点击后收掉浏览器默认 focus 外框；键盘导航保留细描边兜底 */
.type-segmented__item:focus {
  outline: none;
}

.type-segmented__item:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

.type-segmented__item:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.type-segmented__item.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
}

.filter-panel {
  display: flex;
  width: 100%;
  max-height: 72vh;
}

/* 左侧分类导航：固定宽度，与右侧内容以竖线分隔 */
.filter-panel__sidebar {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 120px;
  padding: 12px 0;
  border-right: 1px solid var(--border-light);
}

.filter-panel__nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  background-color: transparent;
  border: none;
  border-right: 2px solid transparent;
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-right-color 150ms ease;
}

.filter-panel__nav:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.filter-panel__nav.is-active {
  font-weight: 500;
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-right-color: var(--brand-500);
}

.filter-panel__nav-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 分类下已选项数角标：与入口按钮角标同一语言 */
.filter-panel__nav-count {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 6px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  color: var(--bg-card);
  background-color: var(--brand-700);
  border-radius: var(--radius-pill);
}

/* 右侧主体：上下分区，内容区滚动、底部固定 */
.filter-panel__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

/* 内容区：单类选项平铺展示，占满剩余高度并独立滚动 */
.filter-panel__body {
  flex: 1;
  min-height: 0;
  padding: 12px 16px;
  overflow-y: auto;
}

.filter-panel__section + .filter-panel__section {
  margin-top: 16px;
}

.filter-panel__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 筛选胶囊：默认中性描边；选中态类型走品牌软底，标签走标签色实底（chipStyle 注入） */
.filter-chip {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.filter-chip:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.filter-chip.is-selected {
  font-weight: 500;
  color: var(--chip-color, var(--brand-700));
  background-color: var(--chip-bg, var(--brand-100));
  border-color: var(--chip-border, var(--brand-400));
}

/* 胶囊左侧状态区：仅未选中标签胶囊显示色点；选中态无前缀，避免宽度跳动 */
.filter-chip__prefix {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
}

.filter-chip__dot {
  width: 8px;
  height: 8px;
  background-color: var(--text-tertiary);
  border-radius: 50%;
}

.filter-panel__empty {
  margin: 4px 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 底部固定操作栏：重置 / 已选计数 / 取消 / 确定 永远可见 */
.filter-panel__footer {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border-light);
}

.filter-panel__count {
  flex: 1;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
}

.filter-panel__search {
  width: 100%;
  margin-bottom: 8px;
}

.filter-panel__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
