<script setup lang="ts">
import { Close, Plus } from "@element-plus/icons-vue";
import { buildAssetSubtitle, shouldShowAssetCode } from "@/utils/assetDisplay";
import type { WatchlistItem } from "@/api/watchlist";

/**
 * 分组抽屉的单栏列表（#980 拆分自 `GroupItemsDialog.vue`）。
 *
 * 左右两栏结构同源、行为相反：
 * - `member`（左）：本组产品，行尾「×」移除；
 * - `candidate`（右）：可添加候选，行首「+」加入，整行可点（键盘 Enter 同效）。
 *
 * 视觉语言与 `TagManagerDialog` 的「白底卡片列表」一致；样式随组件走，
 * 父级只保留双栏栅格，因此两栏宽度/滚动行为不受拆分影响。
 */
defineOptions({ name: "GroupItemColumn" });

const props = withDefaults(
  defineProps<{
    title: string;
    /** 右上的计数文案（如「3 项」「12 项可添加」），由父级按口径拼好 */
    countLabel: string;
    /** 空态文案 */
    emptyText: string;
    items: WatchlistItem[];
    variant?: "member" | "candidate";
  }>(),
  { variant: "member" }
);

const emit = defineEmits<{
  add: [item: WatchlistItem];
  remove: [item: WatchlistItem];
}>();

const isCandidate = () => props.variant === "candidate";

/** 虚拟持仓行无自选记录 id，无法作为列表 key，退回 symbol */
function itemKey(item: WatchlistItem): string | number {
  return item.id ?? item.symbol;
}

function subtitleOf(item: WatchlistItem): string {
  return buildAssetSubtitle(item);
}

function showCode(item: WatchlistItem): boolean {
  return shouldShowAssetCode(item);
}
</script>

<template>
  <section class="gi-col">
    <header class="gi-col__head">
      <span class="gi-col__title">{{ title }}</span>
      <span class="gi-count">{{ countLabel }}</span>
    </header>
    <div class="gi-card" :class="{ 'gi-card--picker': isCandidate() }">
      <p v-if="items.length === 0" class="gi-empty">{{ emptyText }}</p>
      <ul v-else class="gi-list">
        <li
          v-for="item in items"
          :key="itemKey(item)"
          class="gi-row"
          :class="{ 'gi-row--pick': isCandidate() }"
        >
          <!-- 点击整行或右侧「+」即加入本组（加入后该行随即进入左栏「本组产品」，
               并从右栏候选消失）。用明确的「+」按钮替代原「恒为未勾选的 checkbox」：
               原实现 checkbox 永远不显示勾选态、看起来像失效控件，属于误报式 UX bug。 -->
          <el-button
            v-if="isCandidate()"
            class="gi-add-btn"
            size="small"
            circle
            text
            :title="`添加到本组：${item.display_name}`"
            @click.stop="emit('add', item)"
          >
            <el-icon><Plus /></el-icon>
          </el-button>
          <div
            class="gi-row__main"
            :role="isCandidate() ? 'button' : undefined"
            :tabindex="isCandidate() ? 0 : undefined"
            @keydown.enter="isCandidate() && emit('add', item)"
            @click="isCandidate() && emit('add', item)"
          >
            <span class="gi-name">{{ item.display_name }}</span>
            <span v-if="showCode(item)" class="gi-code">{{ item.symbol }}</span>
            <span v-else-if="subtitleOf(item)" class="gi-code">{{
              subtitleOf(item)
            }}</span>
          </div>
          <el-button
            v-if="!isCandidate()"
            class="gi-icon-btn"
            size="small"
            text
            :title="`从本组移除 ${item.display_name}`"
            @click="emit('remove', item)"
          >
            <el-icon><Close /></el-icon>
          </el-button>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.gi-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.gi-col__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
}

.gi-col__title {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

/* 计数：tabular-nums 防止数字变化时宽度抖动 */
.gi-count {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 列表容器：细边卡片，与 TagManagerDialog 的「白底卡片列表」同语言；
   抽屉内高度受限，用 60vh 留出搜索框与表头空间 */
.gi-card {
  max-height: 60vh;
  padding: var(--space-2);
  overflow-y: auto;
  background-color: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.gi-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.gi-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-1) var(--space-2);
  background-color: var(--bg-card);
  border-radius: var(--radius-sm);
  transition: background-color 150ms ease;
}

.gi-row--pick:hover {
  background-color: var(--bg-hover);
}

/* 候选行：整行可点（点击 = 加入本组），光标提示可点 */
.gi-row--pick .gi-row__main {
  cursor: pointer;
}

.gi-row__main {
  display: flex;
  flex: 1;
  gap: var(--space-2);
  align-items: baseline;
  min-width: 0;
}

.gi-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.gi-code {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 移除按钮：默认弱化可见，行 hover 才全亮（与表格操作列同一弱化语言） */
.gi-icon-btn {
  flex-shrink: 0;
  color: var(--text-tertiary-ink);
  opacity: 0.55;
  transition:
    opacity 150ms ease,
    color 150ms ease,
    background-color 150ms ease;
}

.gi-row:hover .gi-icon-btn {
  opacity: 1;
}

.gi-icon-btn:hover {
  color: var(--color-danger);
  background-color: var(--bg-hover);
}

.gi-empty {
  padding: var(--space-3) 0;
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

/* 「+」添加按钮：右缘弱化的圆形图标按钮，整行 hover 才全亮，与行内移除按钮同语言 */
.gi-add-btn {
  flex-shrink: 0;
  margin-right: 0;
  color: var(--text-tertiary-ink);
  opacity: 0.55;
  transition:
    opacity 150ms ease,
    color 150ms ease,
    background-color 150ms ease;
}

.gi-row--pick:hover .gi-add-btn {
  opacity: 1;
}

.gi-add-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
}
</style>
