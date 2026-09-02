<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistFilterBar 同模式） */
import { computed } from "vue";
import { Search } from "@element-plus/icons-vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import type { WatchlistGroup } from "@/api/watchlist";

defineOptions({ name: "WatchlistToolbar" });

const props = defineProps<{
  toolbar: WatchlistToolbarState;
  customGroups: WatchlistGroup[];
  toggleBtnText: string;
}>();

const emit = defineEmits<{
  (e: "search-input", value: string): void;
  (e: "batch-move", groupId: number | null): void;
  (e: "batch-delete"): void;
  (e: "exit-batch"): void;
  (e: "add"): void;
  (e: "refresh"): void;
  (e: "export"): void;
  (e: "ocr"): void;
  (e: "toggle-realtime"): void;
  (e: "open-settings"): void;
}>();

// 状态注入模式：toolbar 为 composable 实例 prop，v-model 需经 computed 桥接其内部 ref
const searchKeywordModel = computed({
  get: () => props.toolbar.searchKeyword.value,
  set: (value: string) => {
    props.toolbar.searchKeyword.value = value;
  }
});

const batchMoveGroupIdModel = computed({
  get: () => props.toolbar.batchMoveGroupId.value,
  set: (value: number | null) => {
    props.toolbar.batchMoveGroupId.value = value;
  }
});

function handleSearchInput(value: string) {
  emit("search-input", value);
}
</script>

<template>
  <!-- 顶部操作栏 (已移除 size="small" 和 CSS 强制 32px 高度) -->
  <div class="flex flex-wrap items-center justify-between gap-4 mb-6 top-bar">
    <div class="flex items-center gap-3">
      <div class="flex items-center relative">
        <el-input
          v-model="searchKeywordModel"
          placeholder="搜索当前自选列表..."
          clearable
          class="w-48"
          :prefix-icon="Search"
          @input="handleSearchInput"
        />
        <el-tooltip
          content="在当前自选列表中按代码或名称过滤"
          placement="bottom-start"
          :offset="8"
        >
          <IconifyIconOffline
            icon="ep:info-filled"
            class="absolute right-[-22px] top-1/2 -translate-y-1/2 text-sm cursor-help transition-colors"
            :style="{ color: 'var(--text-tertiary)' }"
          />
        </el-tooltip>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <!-- 批量模式下的特殊工具栏 -->
      <template v-if="toolbar.batchMode.value">
        <div class="flex items-center gap-3">
          <span
            class="text-sm font-medium shrink-0"
            :style="{ color: 'var(--text-primary)' }"
          >
            已选 {{ toolbar.selectedItems.value.length }} 项
          </span>
          <el-select
            v-model="batchMoveGroupIdModel"
            placeholder="移动到分组"
            class="batch-move-select"
            clearable
            @change="emit('batch-move', batchMoveGroupIdModel)"
          >
            <el-option
              v-for="group in customGroups"
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
            @click="emit('batch-delete')"
          >
            <IconifyIconOffline icon="ep:delete" class="mr-1" />
            删除选中
          </el-button>
          <el-button type="primary" @click="emit('exit-batch')">
            退出批量模式
          </el-button>
        </div>
      </template>

      <!-- 正常模式下的工具栏：主按钮「添加自选」 + 轻量图标操作（刷新/导出/AI导入/实时估值）+ 管理入口 -->
      <template v-else>
        <el-button type="primary" @click="emit('add')">
          <IconifyIconOffline icon="ep:plus" class="mr-1" />
          添加自选
        </el-button>

        <el-tooltip content="刷新" placement="bottom">
          <el-button circle class="icon-tool-btn" @click="emit('refresh')">
            <IconifyIconOffline icon="ep:refresh" />
          </el-button>
        </el-tooltip>

        <el-tooltip content="导出" placement="bottom">
          <el-button circle class="icon-tool-btn" @click="emit('export')">
            <IconifyIconOffline icon="ep:download" />
          </el-button>
        </el-tooltip>

        <el-tooltip content="AI 导入" placement="bottom">
          <el-button circle class="icon-tool-btn" @click="emit('ocr')">
            <IconifyIconOffline icon="ep:magic-stick" />
          </el-button>
        </el-tooltip>

        <!-- 实时估值开关：状态色区分（开启 = 品牌色高亮，关闭 = 中性弱化），tooltip 给全文案 -->
        <el-tooltip :content="toggleBtnText" placement="bottom">
          <el-button
            circle
            class="icon-tool-btn"
            :class="{ 'is-active': toggleBtnText.includes('关闭') }"
            @click="emit('toggle-realtime')"
          >
            <IconifyIconOffline icon="mdi:lightning-bolt" />
          </el-button>
        </el-tooltip>

        <el-button plain @click="emit('open-settings')">
          <IconifyIconOffline icon="ep:setting" class="mr-1" />
          管理
        </el-button>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* ======================================
   轻量图标操作按钮（刷新/导出/AI导入/实时估值）
   默认中性弱化，hover 提亮；实时开关开启态品牌色高亮（视觉降噪，避免多个文字按钮挤一排）
   ====================================== */
.icon-tool-btn {
  width: 32px;
  height: 32px;
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

.icon-tool-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.icon-tool-btn.is-active {
  color: var(--brand-700);
  border-color: var(--brand-400);
}

.icon-tool-btn.is-active:hover {
  background-color: var(--brand-100);
}

/* ======================================
   批量模式工具栏优化
   ====================================== */
.batch-move-select {
  min-width: 180px;
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

.batch-move-select :deep(.el-input__suffix) {
  display: flex;
  align-items: center;
}

.batch-move-select :deep(.el-input__wrapper:hover) {
  border-color: var(--brand-500);
}

.batch-move-select :deep(.el-input__wrapper.is-focus) {
  border-color: var(--brand-700);
  box-shadow: var(--focus-ring);
}

/* 删除选中按钮：幽灵危险按钮 */
.batch-delete-btn {
  color: var(--color-danger);
  background-color: transparent;
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;
}

.batch-delete-btn:hover {
  color: #fff;
  background-color: var(--color-danger);
  border-color: var(--color-danger);
}

.batch-delete-btn:active {
  transform: translateY(1px);
}

.batch-delete-btn:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
  border-color: var(--text-disabled);
  opacity: 0.5;
}

.batch-delete-btn:disabled:hover {
  color: var(--text-disabled);
  background-color: transparent;
}

/* 吸顶兜底：主方案由表格内部滚动使页面不滚动、操作栏本就常驻；
   此处仅在极端配置导致整页滚动时让操作栏吸顶常驻，背景与页面底一致避免内容穿透 */
.top-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  padding-bottom: 12px;
  margin-bottom: 12px;
  background: var(--bg-page);
}
</style>
