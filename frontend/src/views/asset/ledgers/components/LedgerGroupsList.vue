<template>
  <!-- 按类型分组的账户卡片列表；外层 ledger-groups 供「分组顺序拖拽」，与卡片拖拽互相独立 -->
  <div ref="groupsContainer" class="ledger-groups">
    <div
      v-for="(group, gi) in p.displayedGroups"
      :key="group.type"
      class="mb-8 ledger-group"
      :class="{
        'ledger-group--dragging': group.type === p.draggingGroupType
      }"
    >
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-1 min-w-0">
          <!-- 分组拖拽抓手：与卡片抓手视觉/作用域分离，hover/focus 显示，拖拽整个分组（分组顺序存 localStorage） -->
          <span
            class="group-drag-handle"
            role="button"
            tabindex="0"
            :aria-label="`调整分组顺序：${group.label}，当前第 ${gi + 1} / ${p.displayedGroups.length} 位，用上下方向键移动`"
            :title="`拖动或用方向键调整分组顺序：${group.label}`"
            @click.stop
            @keydown.enter.stop
            @keydown.up.stop.prevent="onGroupKey(group, gi, gi - 1)"
            @keydown.down.stop.prevent="onGroupKey(group, gi, gi + 1)"
            @keydown.home.stop.prevent="onGroupKey(group, gi, 0)"
            @keydown.end.stop.prevent="
              onGroupKey(group, gi, p.displayedGroups.length - 1)
            "
          >
            <!-- 分组拖拽：纵向三横线「块」抓手，暗示整段分组重排，与卡片四向箭头明确区分 -->
            <svg
              class="drag-grip drag-grip--group"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              aria-hidden="true"
            >
              <line x1="6" y1="6" x2="18" y2="6" />
              <line x1="6" y1="12" x2="18" y2="12" />
              <line x1="6" y1="18" x2="18" y2="18" />
            </svg>
          </span>
          <h3
            class="font-semibold text-base"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ group.label }}
            <span
              class="text-sm font-normal ml-2"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              (
              {{ group.count }} 个账户 ·
              <MoneyDisplay
                :value="group.total"
                :show-sign="false"
                :auto-color="false"
                size="xs"
              />)
            </span>
          </h3>
        </div>
      </div>

      <!-- 账户卡片：auto-fit 网格自动折叠空轨道，孤点分类不会产生右侧大片空白。
             卡片展示细节已拆分至 components/LedgerCard.vue（#984）。
             网格绑定 data-ledger-type 供 sortablejs 按类型初始化拖拽（仅同组内可拖）。 -->
      <div class="ledger-grid" :data-ledger-type="group.type">
        <LedgerCard
          v-for="(ledger, li) in group.ledgers"
          :key="ledger.id"
          :ledger="ledger"
          :index="Number(li)"
          :total="group.ledgers.length"
          :stale-count="p.staleCountByLedger[ledger.id] || 0"
          @open="p.goToDetail"
          @delete="p.openDeleteDialog"
          @toggle-archive="p.onToggleArchive"
          @reorder-key="onCardKey"
        />
      </div>

      <!-- 幽灵态新增占位符：胶囊小按钮，高度恒定 44px，不撑满网格行。
             携带分组类型打开弹窗，预置账户类型（#1082 入口预填） -->
      <button
        type="button"
        class="ghost-add"
        :aria-label="`新增${p.getChannelCategoryLabel(group.type)}`"
        @click="p.openCreateDialog(group.type)"
      >
        <IconifyIconOffline icon="ep:plus" class="ghost-add__icon" />
        <span>新增{{ p.getChannelCategoryLabel(group.type) }}</span>
      </button>
    </div>

    <!-- 键盘重排结果播报（#1841）：顺序变化在视觉上只是卡片换位，不播报则屏幕阅读器
         用户完全感知不到。role=status + aria-live=polite：只在播报文本变化时读一次。 -->
    <p class="a11y-live" role="status" aria-live="polite">{{ announce }}</p>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import LedgerCard from "./LedgerCard.vue";
import type { useLedgerList } from "../composables/useLedgerList";

defineOptions({ name: "LedgerGroupsList" });

/**
 * 账户列表页分组卡片区（#980 P1-C 结构拆分）：
 * 分组头（抓手/金额汇总）+ 账户卡片网格（Sortable 拖拽）+ 分组幽灵新增按钮。
 * page 为 index 注入的状态单体；p 用 reactive 解包，使模板表达式与拆分前逐字一致。
 */
const props = defineProps<{ page: ReturnType<typeof useLedgerList> }>();
const p = reactive(props.page);

// ── 键盘重排（#1841）──
// 拖拽此前是唯一的排序方式，抓手还是 tabindex="-1"，键盘用户完全无法调整顺序
// （WCAG 2.1.1）。现在两个抓手都可聚焦：↑/↓ 移动一位、Home/End 移到首尾，
// 落库与拖拽走同一函数。播报走 aria-live——顺序变了但视觉上只是卡片换位，
// 屏幕阅读器用户若不播报会完全感知不到。
const announce = ref("");

/** 方向键 → 目标下标（Home/End 传 ±Infinity，由 composable 收敛到边界） */
function onGroupKey(
  group: { type: string; label: string },
  from: number,
  to: number
) {
  if (p.moveGroupByKeyboard(group.type, to)) {
    announce.value = `${group.label} 已移到第 ${to + 1} 位（共 ${p.displayedGroups.length} 组）`;
  } else {
    // 已在首/尾：明确说「没动」，否则用户以为按键坏了
    announce.value = `${group.label} 已在${to < from ? "最前" : "最后"}，位置未变`;
  }
}

async function onCardKey(payload: { ledger: any; to: number }) {
  const { ledger, to } = payload;
  const group = p.displayedGroups.find(g =>
    g.ledgers.some((l: any) => l.id === ledger.id)
  );
  if (!group) return;
  const total = group.ledgers.length;
  const ok = await p.moveLedgerByKeyboard(group.type, ledger.id, to);
  if (!ok) {
    // 已在首位/末位，或落库失败（composable 已提示并回滚）——这里不再重复播报
    return;
  }
  announce.value = `${ledger.name} 已移到第 ${to + 1} 位（本组共 ${total} 个账户）`;
}

/* 分组容器 DOM ref：模板字符串 ref 命中本组件 setup 同名绑定即写入 .value，
   与 useLedgerList 内 groupsContainer 指向同一 Ref，分组拖拽初始化不受拆分影响 */
const groupsContainer = props.page.groupsContainer;
</script>

<style scoped>
/* 尊重系统减弱动效偏好：抓手/占位/账户卡片动效关闭
   （自 index 原整块按选择器拆分，LedgerCard 内部规则见其 scoped 块） */
@media (prefers-reduced-motion: reduce) {
  .ghost-add,
  .ledger-card {
    transition: none;
  }

  .ledger-card:hover {
    transform: none;
  }
}

/* 分组拖拽抓手：常驻低透明，hover/focus 高亮，与卡片抓手区分（分组顺序本地存储） */
.group-drag-handle {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--text-tertiary-ink);
  touch-action: none;
  cursor: grab;
  border-radius: var(--radius-sm);
  opacity: 0.5;
  transition:
    opacity 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}

.group-drag-handle:active {
  cursor: grabbing;
}

.ledger-group:hover .group-drag-handle,
.group-drag-handle:hover {
  color: var(--brand-600);
  background: var(--bg-page);
  opacity: 1;
}

/* 分组抓手：纵向三横线「块」抓手，描边风格 */
.drag-grip--group {
  padding: 2px;
}

/* 分组拖拽中的占位「幽灵」态 */
.ledger-group--ghost {
  opacity: 0.4;
}

/* 分组拖拽中：整段高亮，强化「正在重排整段分组」的反馈（与卡片拖拽态分层） */
.ledger-group--dragging {
  background: var(--brand-100);
  border-radius: var(--radius-lg);
  box-shadow: 0 0 0 2px var(--brand-300);
}

/* ===== 账户卡片网格：auto-fit 自动折叠空轨道，孤点分类不产生右侧大片空白 ===== */
.ledger-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr));
  gap: var(--space-compact);
}

/* ===== 幽灵态新增占位符：--bg-soft 底、胶囊圆角、高度恒定 44px ===== */
.ghost-add {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 44px;
  padding: 0 var(--space-compact);
  margin-top: var(--space-compact);
  font-family: inherit;
  font-size: var(--text-small, 14px);
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-soft);
  border: none;
  border-radius: var(--radius-pill);
  transition: background-color 0.15s ease;
}

.ghost-add:hover {
  background: var(--bg-hover);
}

.ghost-add:focus-visible {
  box-shadow: var(--focus-ring);
}

.ghost-add__icon {
  font-size: 14px;
}

/* 视觉隐藏但保留给屏幕阅读器（#1841）。
   不用 display:none / visibility:hidden —— 那会让 aria-live 区域彻底不被播报。
   clip-path + 1px 尺寸是现代做法，不再依赖 clip:rect() 的废弃写法。 */
.a11y-live {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  white-space: nowrap;
  border: 0;
  clip-path: inset(50%);
}
</style>
