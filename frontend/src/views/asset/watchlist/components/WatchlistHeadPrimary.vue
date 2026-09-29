<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：toolbar/data/groups 为
   composable 实例 prop，经 computed get/set 桥接修改其内部 ref 属有意设计
   （与 WatchlistFilterBar 同模式） */
import { computed } from "vue";
import { Search } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";
import type { useWatchlistData } from "@/composables/useWatchlistData";

/**
 * 双行分区头部「第一行」.head-primary（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 批量模式 = 整行切换为批量工具条；正常模式 = 搜索占左、快捷工具图标
 * （刷新/导出/AI 导入/实时估值）+ 核心操作（管理/添加自选）居右。
 * 不吸顶：作为滚动内容首行，下滚时自然滚出视口（搜索框「自动隐藏」）。
 * 纯展示 + 事件转发：状态全部在 toolbar/data/groups 三个 composable，本组件不持有业务状态。
 */
const props = defineProps<{
  toolbar: ReturnType<typeof useWatchlistToolbar>;
  data: ReturnType<typeof useWatchlistData>;
  groups: ReturnType<typeof useWatchlistGroups>;
  /** 实时估值开关按钮文案（来自 useWatchlistValuation.toggleBtnText） */
  toggleBtnText: string;
}>();

const emit = defineEmits<{
  /** 实时估值开关点击 → 页面转发 realtime.toggle()（realtime 不注入本组件） */
  (e: "toggle-realtime"): void;
}>();

// 状态注入模式：toolbar 内部 ref 经 computed get/set 桥接双向绑定（v-model）
const searchKeyword = computed({
  get: () => props.toolbar.searchKeyword.value,
  set: (value: string) => {
    props.toolbar.searchKeyword.value = value;
  }
});
const batchMoveGroupId = computed({
  get: () => props.toolbar.batchMoveGroupId.value,
  set: (value: number | undefined) => {
    props.toolbar.batchMoveGroupId.value = value;
  }
});
</script>

<template>
  <div class="head-primary">
    <!-- 批量模式：第一行整行切换为批量工具条 -->
    <template v-if="toolbar.batchMode.value">
      <span
        class="text-sm font-medium shrink-0"
        :style="{ color: 'var(--text-primary)' }"
      >
        已选 {{ toolbar.selectedItems.value.length }} 项
      </span>
      <el-select
        v-model="batchMoveGroupId"
        placeholder="移动到分组"
        class="batch-move-select"
        clearable
        @change="data.handleBatchMoveToGroup"
      >
        <el-option
          v-for="group in groups.customGroups.value"
          :key="group.id"
          :label="group.name"
          :value="group.id"
        >
          <div class="flex items-center gap-2">
            <!-- 数据色例外：分组色为用户数据（非设计令牌），缺失时回退中性 token -->
            <span
              class="w-2.5 h-2.5 rounded-full"
              :style="{
                backgroundColor: group.color || 'var(--text-tertiary)'
              }"
            />
            <span>{{ group.name }}</span>
          </div>
        </el-option>
      </el-select>
      <el-button
        class="batch-delete-btn"
        :disabled="toolbar.selectedItems.value.length === 0"
        @click="data.handleBatchDelete"
      >
        <IconifyIconOffline icon="ep:delete" class="mr-1" />
        删除选中
      </el-button>
      <el-button type="primary" @click="toolbar.toggleBatchMode">
        退出批量模式
      </el-button>
    </template>

    <!-- 正常模式：搜索占左、核心操作 + 快捷工具居右，中间留白呼吸。
         布局修订（2026-09-05）：原第二行的「刷新/导出/AI 导入/实时估值」图标组
         并入本行（用户反馈第二行因分组 Tab + 筛选 + 图标组共挤一行显拥挤、
         本行反而空），行内从左到右为「图标组(次级工具) | 管理(次级) | 添加自选
         (主 CTA 最右)」，图标组前不再加 divider（其左侧本就是行间留白）。 -->
    <template v-else>
      <div class="head-primary__search">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索自选..."
          clearable
          :prefix-icon="Search"
          class="watchlist-search"
          @input="data.debounceSearch"
        />
        <el-tooltip
          content="在当前自选列表中按代码或名称过滤"
          placement="bottom-start"
          :offset="8"
        >
          <IconifyIconOffline
            icon="ep:info-filled"
            class="search-hint text-sm cursor-help transition-opacity"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          />
        </el-tooltip>
      </div>
      <div class="head-primary__actions">
        <!-- 快捷工具图标组（原 WatchlistFilterBar #actions，2026-09-05 上移本行）：
             刷新 / 导出 / AI 导入 / 实时估值开关。实时开启态品牌色高亮见 .icon-tool-btn.is-active -->
        <div v-if="!toolbar.batchMode.value" class="header-actions">
          <el-tooltip content="刷新" placement="bottom">
            <el-button circle class="icon-tool-btn" @click="data.fetchData()">
              <IconifyIconOffline icon="ep:refresh" />
            </el-button>
          </el-tooltip>

          <el-tooltip content="导出" placement="bottom">
            <el-button circle class="icon-tool-btn" @click="data.exportData">
              <IconifyIconOffline icon="ep:download" />
            </el-button>
          </el-tooltip>

          <el-tooltip content="AI 导入" placement="bottom">
            <el-button
              circle
              class="icon-tool-btn"
              @click="toolbar.openOcrDialog"
            >
              <IconifyIconOffline icon="ep:magic-stick" />
            </el-button>
          </el-tooltip>

          <!-- 实时估值开关：开启 = 品牌色高亮（tooltip「关闭实时估值」），关闭 = 中性弱化 -->
          <el-tooltip :content="toggleBtnText" placement="bottom">
            <el-button
              circle
              class="icon-tool-btn"
              :class="{ 'is-active': toggleBtnText.includes('关闭') }"
              @click="emit('toggle-realtime')"
            >
              <IconifyIconOffline icon="ep:lightning" />
            </el-button>
          </el-tooltip>
        </div>
        <!-- 图标组与核心操作之间的细分隔线（design.md 卡片内分割线） -->
        <div class="head-divider" aria-hidden="true" />
        <el-button plain @click="toolbar.openSettingsDrawer">
          <IconifyIconOffline icon="ep:setting" class="mr-1" />
          管理
        </el-button>
        <el-button type="primary" @click="toolbar.openAddDialog">
          <IconifyIconOffline icon="ep:plus" class="mr-1" />
          添加自选
        </el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ======================================
   双行分区头部（#1281 第四轮修订，2026-09-05）
   —— 第一行 .head-primary：搜索框 + 快捷工具图标（刷新/导出/AI导入/实时估值，
      2026-09-05 从第二行上移）+ 核心操作（管理 / 添加自选，主 CTA 最右）；
      第二行由 WatchlistFilterBar 承载「分组 Tab（最左）+ 标签筛选/视图/新建」。
   两行各自 justify-between / 左紧右松，主次分离；控件统一 32px 高、
   同一垂直基线。
   ====================================== */

/* 搜索 + 核心操作区：固定高度由内容撑出，与下方筛选行间距 12px（--space-3）。
   （2026-09-06 呼吸感回调：原 6px 使「搜索行 / 分组筛选行 / 表头」三带几乎贴合成
   一条，缺少分区层级；回到规范间距后各带边界可辨，代价约 6px 首屏高度。）
   不吸顶：作为滚动内容首行，页面下滚时自然滚出视口（即「搜索框自动隐藏」），
   无需 JS 收起动画。max-height 40px 上限防止内容意外溢出（原紧凑态折叠机制
   已于 2026-09-05 根因修复时随外层滚动架构废弃）。 */
.head-primary {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  max-height: 40px;
  margin-bottom: var(--space-3);
  overflow: hidden;
  transition:
    max-height 200ms ease,
    margin-bottom 200ms ease,
    opacity 150ms ease;
}

/* 搜索区：固定 240px（2026-09-05 修订）。
   此前设为 flex:1 + max-width 560，输入框被拉得过长、与右侧按钮组失衡，
   且「搜索自选」只是 4~6 字提示，240px 已足够容纳代码/名称输入。 */
.head-primary__search {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.watchlist-search {
  width: 240px;
}

/* 核心操作按钮组：次级（管理）32px + 主按钮（添加自选）36px，同一垂直基线居中。
   尺寸规范（2026-09-05）：主按钮 36 / 次级文字按钮 32 / 纯图标按钮 28。 */
.head-primary__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
  align-items: center;
}

.head-primary__actions :deep(.el-button--primary) {
  height: 36px;
}

/* 快捷工具图标组（原 FilterBar #actions，2026-09-05 上移 head-primary）：等距排布 */
.header-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

/* 快捷图标组与核心操作（管理/添加自选）之间的细分隔线 */
.head-divider {
  flex-shrink: 0;
  width: 1px;
  height: 20px;
  margin: 0 2px;
  background-color: var(--border-light);
}

/* 轻量图标操作按钮（刷新/导出/AI导入/实时估值）
   尺寸规范：纯图标按钮统一 28×28（与主按钮 36、次级按钮 32 形成三级梯度）；
   默认中性弱化线框，hover 提亮；实时开关开启态填品牌实底 */
.icon-tool-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.icon-tool-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

/* 实时开启态：品牌色实底高亮——开关在图标组里是否可见/是否已开，一眼可辨 */
.icon-tool-btn.is-active {
  /* #1600：文字原用 --brand-100，但该令牌在暗色下翻成深色 #2D1612 → 在实底上仅 3.65:1；
     改用 --text-inverse（两套主题恒为 #fff），亮 4.92:1 / 暗 4.66:1 均达 AA。 */
  color: var(--text-inverse);
  background-color: var(--brand-solid);
  border-color: var(--brand-solid);
}

.icon-tool-btn.is-active:hover {
  background-color: var(--brand-solid-hover);
  border-color: var(--brand-solid-hover);
}

/* 说明图标：默认可见，滚动进入紧凑态时淡出（规则见下「紧凑态」） */
.search-hint {
  opacity: 1;
  transition: opacity 150ms ease;
}

/* 批量模式：移动到分组下拉 */
.batch-move-select {
  width: 160px;
}

.batch-move-select :deep(.el-input__wrapper) {
  padding-top: 0;
  padding-bottom: 0;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  box-shadow: none;
  transition: all 0.2s ease;
}

.batch-move-select :deep(.el-input__wrapper:hover) {
  border-color: var(--brand-500);
}

.batch-move-select :deep(.el-input__wrapper.is-focus) {
  border-color: var(--brand-700);
  box-shadow: var(--focus-ring);
}

/* 批量模式：删除选中（幽灵危险按钮） */
.batch-delete-btn {
  color: var(--color-danger);
  background-color: transparent;
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;
}

.batch-delete-btn:hover {
  color: var(--text-inverse);
  background-color: var(--color-danger);
  border-color: var(--color-danger);
}

.batch-delete-btn:active {
  transform: translateY(1px);
}

.batch-delete-btn:disabled {
  /* audit-text-contrast: exempt .batch-delete-btn:disabled 为**真禁用**控件，按 WCAG 1.4.3 对 inactive component 的豁免；**「无数据占位符」不适用本豁免**（那是信息，须用 --text-tertiary-ink）。登记见 docs/spec/tech-debt.md（#1599） */
  color: var(--text-disabled);
  cursor: not-allowed;
  border-color: var(--text-disabled);
  opacity: 0.5;
}

.batch-delete-btn:disabled:hover {
  /* audit-text-contrast: exempt .batch-delete-btn:disabled:hover 为**真禁用**控件，按 WCAG 1.4.3 对 inactive component 的豁免；**「无数据占位符」不适用本豁免**（那是信息，须用 --text-tertiary-ink）。登记见 docs/spec/tech-debt.md（#1599） */
  color: var(--text-disabled);
  background-color: transparent;
}
</style>
