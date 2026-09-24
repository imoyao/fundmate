<template>
  <div class="filter-panel">
    <aside class="filter-panel__sidebar">
      <button
        type="button"
        class="filter-panel__nav"
        :class="{ 'is-active': activePanel === 'type' }"
        @click="updateActivePanel('type')"
      >
        <span class="filter-panel__nav-text">产品类型</span>
        <span v-if="draftTypes.length" class="filter-panel__nav-count">
          {{ draftTypes.length }}
        </span>
      </button>
      <button
        type="button"
        class="filter-panel__nav"
        :class="{ 'is-active': activePanel === 'tag' }"
        @click="updateActivePanel('tag')"
      >
        <span class="filter-panel__nav-text">资产标签</span>
        <span v-if="draftTagIds.length" class="filter-panel__nav-count">
          {{ draftTagIds.length }}
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
                  'is-selected': draftTypes.includes(t)
                }"
                @click="emit('toggle-type', t)"
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
          <section class="filter-panel__section filter-panel__section--tags">
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
                  'is-selected': draftTagIds.includes(t.id)
                }"
                :style="chipStyle(t)"
                @click="emit('toggle-tag', t.id)"
              >
                <span
                  v-if="!draftTagIds.includes(t.id)"
                  class="filter-chip__prefix"
                >
                  <span
                    class="filter-chip__dot"
                    :style="{ backgroundColor: t.color || undefined }"
                  />
                </span>
                {{ t.name }}
              </button>
              <p v-if="filteredTags.length === 0" class="filter-panel__empty">
                无匹配标签
              </p>
            </div>
          </section>
        </template>
      </div>

      <!-- 底部固定操作栏经 slot 嵌入（由 FilterPanelPopover 提供），
           保持原 DOM 结构：.filter-panel__main > [.filter-panel__body, footer] -->
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistTag } from "@/api/watchlist";
import { DEFAULT_TAG_COLOR } from "@/constants/watchlist";
import { assetTypeLabel } from "@/composables/useEnumLabels";

/**
 * 筛选弹层主体（#980 P0-b 拆分自 FilterPanelPopover，零行为变更）：
 * 左侧分类导航 + 右侧「产品类型 / 资产标签」两组草稿多选区。
 * 草稿真源在 FilterPanelPopover（打开时同步、确定时提交），本组件只经
 * props 接收草稿值、经 emit 上抛切换动作；groups / tags 为状态注入。
 */
const props = defineProps<{
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  activePanel: "type" | "tag";
  draftTypes: string[];
  draftTagIds: number[];
}>();

const emit = defineEmits<{
  (e: "update:active-panel", value: "type" | "tag"): void;
  /** 切换类型草稿选中态（父级 FilterPanelPopover 持有草稿真源并原地修改） */
  (e: "toggle-type", value: string): void;
  /** 切换标签草稿选中态 */
  (e: "toggle-tag", value: number): void;
}>();

function updateActivePanel(value: "type" | "tag"): void {
  emit("update:active-panel", value);
}

// ── 类型多选（弹层内与标签正交组合，见 FilterPanelPopover 头注释）──
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

// 当前是否在「持仓」分组：持仓分组只有真实持仓（股票 / 基金类），
// 经理 / 组合 / 指数等无持仓语义的类型在此视图下不可选。
const isHoldingGroup = computed(
  () => props.groups.activeGroup.value === "holding"
);
// 弹层内展示的类型选项：持仓分组下收窄为仅股票 / 基金，避免误选无持仓语义的类型。
const visibleTypeOptions = computed<string[]>(() =>
  isHoldingGroup.value ? [...HOLDING_ALLOWED_TYPES] : [...ASSET_TYPE_OPTIONS]
);

// 标签过多时面板内搜索（标签会随使用无限增长，见用户反馈）。
const tagSearch = ref("");
const filteredTags = computed(() => {
  const kw = tagSearch.value.trim().toLowerCase();
  if (!kw) return props.tags.allTags.value;
  return props.tags.allTags.value.filter(t =>
    t.name.toLowerCase().includes(kw)
  );
});

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
</script>

<style scoped>
/* ===== 筛选面板主体（左分类导航 + 右内容）=====
   （样式随模板自 FilterPanelPopover 原样迁入，保持 scoped 作用域不变，零视觉变更） */

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
  color: var(--text-inverse);
  background-color: var(--brand-solid);
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
  color: var(--text-tertiary-ink);
}

.filter-panel__search {
  width: 100%;
  margin-bottom: 8px;
}

.filter-panel__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
