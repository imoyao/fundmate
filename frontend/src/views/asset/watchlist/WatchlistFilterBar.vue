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
import { Files, Folder, Plus } from "@element-plus/icons-vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import type { WatchlistTag } from "@/api/watchlist";
import { DEFAULT_TAG_COLOR } from "@/constants/watchlist";

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
  (e: "tag-apply"): void;
  (e: "tag-clear"): void;
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
const currentViewModel = computed({
  get: () => props.toolbar.currentView.value,
  set: (value: "all" | "exchange" | "otc") => {
    props.toolbar.currentView.value = value;
  }
});
const selectedTagCount = computed(
  () => props.tags.selectedFilterTagIds.value.length
);

// 视图筛选选项（venue 维度）
const viewOptions = [
  { label: "全部", value: "all" },
  { label: "场内", value: "exchange" },
  { label: "场外", value: "otc" }
] as const;

// 打开面板时把已提交筛选同步到草稿（原触发按钮 @click 内的 onTagFilterShow 迁移至此，
// 因 trigger="click" 后开合由 EP 接管，组件不再经手打开动作）
watch(tagFilterVisibleModel, visible => {
  if (visible) props.tags.onTagFilterShow();
});

// 切换视图：同值不重复触发（原 el-segmented v-model+change 行为等价）
function selectView(value: (typeof viewOptions)[number]["value"]) {
  if (currentViewModel.value === value) return;
  currentViewModel.value = value;
  emit("view-change");
}

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

// 一键重置：清空草稿并提交（applyTagFilter 提交空数组即清除标签筛选），关闭面板
function resetFilter() {
  draftFilterTagIdsModel.value = [];
  emit("tag-apply");
  tagFilterVisibleModel.value = false;
}

/** 胶囊颜色：标签色为底（12% 透明度）+ 同色字 + 同色边框（数据色例外，缺失回退 DEFAULT_TAG_COLOR）。
 *  与 TagManagerDialog.pillStyle 保持同一套颜色语言。 */
function chipStyle(tag: WatchlistTag) {
  const c = tag.color || DEFAULT_TAG_COLOR;
  return {
    "--chip-color": c,
    "--chip-bg": `${c}1f`,
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

      <!-- 右段（固定）：分组操作 + 标签筛选 + 视图 segmented，不随分组 tab 滚动 -->
      <div v-if="!toolbar.batchMode.value" class="filter-bar__right">
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

        <!-- 标签筛选（bottom-start 左对齐触发按钮，减少浮层错位感）。
             trigger="click" + v-model:visible：EP 原生接管「点击外部 / Esc 自动收起」，
             替代旧手动 :visible（必须点取消才能关，反直觉）。
             点外部关闭不丢草稿：草稿仅在重新打开时由 watch 重置为已提交筛选 -->
        <el-popover
          v-model:visible="tagFilterVisibleModel"
          trigger="click"
          placement="bottom-start"
          :width="260"
          title="按标签筛选"
        >
          <template #reference>
            <el-button class="tag-filter-btn">
              标签筛选<template v-if="selectedTagCount">
                ({{ selectedTagCount }})
              </template>
            </el-button>
          </template>
          <div class="tag-filter-panel">
            <!-- 标签筛选胶囊（多选）：标签色为底 + 色点 + 名称，与「管理标签」/表格内标签胶囊同一颜色语言 -->
            <div class="tag-filter-chips">
              <button
                v-for="t in allTags"
                :key="t.id"
                type="button"
                class="tag-filter-chip"
                :class="{
                  'is-selected': draftFilterTagIdsModel.includes(t.id)
                }"
                :style="chipStyle(t)"
                @click="toggleDraftTag(t.id)"
              >
                <span
                  class="tag-filter-chip__dot"
                  :style="{
                    backgroundColor: t.color || undefined
                  }"
                />
                {{ t.name }}
              </button>
              <p v-if="allTags.length === 0" class="tag-filter-empty">
                暂无标签，可在「管理」中新建
              </p>
            </div>
            <div class="flex items-center justify-between mt-3">
              <el-button
                size="small"
                text
                type="primary"
                :disabled="
                  draftFilterTagIdsModel.length === 0 && selectedTagCount === 0
                "
                @click="resetFilter"
              >
                重置筛选
              </el-button>
              <div class="flex gap-2">
                <el-button size="small" @click="tagFilterVisibleModel = false">
                  取消
                </el-button>
                <!-- 确定按钮：未勾选任何标签时禁用（勾选草稿后才可提交）。
                     点击「确定」才把草稿提交为生效筛选；期间点标签只改草稿、
                     不动列表，支持连续多选后再一次确定（2026-09-05 交互回归修复） -->
                <el-button
                  size="small"
                  type="primary"
                  :disabled="draftFilterTagIdsModel.length === 0"
                  @click="emit('tag-apply')"
                >
                  确定
                </el-button>
              </div>
            </div>
          </div>
        </el-popover>

        <!-- 视图 segmented：全部 / 场内 / 场外（venue 维度，一级筛选胶囊）。
             手写分段控制器（弃用 el-segmented：JS 绝对定位滑块与自定义尺寸错位，
             见 OcrImportModal 同款决策）；选中态仅浅红底 + 深红字 -->
        <div class="view-segmented" role="tablist" aria-label="视图筛选">
          <button
            v-for="opt in viewOptions"
            :key="opt.value"
            type="button"
            role="tab"
            class="view-segmented__item"
            :class="{ 'is-active': currentViewModel === opt.value }"
            :aria-selected="currentViewModel === opt.value"
            @click="selectView(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
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

/* 标签筛选按钮：32px 胶囊，与分组 tab / segmented 同高（浅色 soft 按钮，未选中 --text-secondary） */
.tag-filter-btn {
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

.tag-filter-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
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

/* ===== 视图分段控制器（全部/场内/场外）：手写，弃用 el-segmented =====
   与分组 tab 同高（轨道 32px）；item 统一几何尺寸，hover/选中仅底色深浅递进，
   文字 flex 居中；选中态仅浅红底 + 深红字，无边框 */
.view-segmented {
  display: flex;
  gap: 2px;
  height: 32px;
  padding: 3px;
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.view-segmented__item {
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
.view-segmented__item:focus {
  outline: none;
}

.view-segmented__item:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

.view-segmented__item:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.view-segmented__item.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
}

.tag-filter-panel {
  max-height: 240px;
  overflow-y: auto;
}

/* 标签筛选胶囊组：flex 换行，多选胶囊（与「管理标签」颜色胶囊同语言） */
.tag-filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* 胶囊：默认中性（--bg-muted + 灰点），选中态以标签色为底（--chip-bg/--chip-color/--chip-border 由 chipStyle 注入） */
.tag-filter-chip {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: var(--bg-muted);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.tag-filter-chip:hover {
  background-color: var(--bg-hover);
}

.tag-filter-chip.is-selected {
  color: var(--chip-color);
  background-color: var(--chip-bg);
  border-color: var(--chip-border);
}

.tag-filter-chip__dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  background-color: var(--text-tertiary);
  border-radius: 50%;
}

.tag-filter-empty {
  margin: 4px 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
