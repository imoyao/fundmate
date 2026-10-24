<script setup lang="ts">
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import LedgerCardMetrics from "./ledgerCard/LedgerCardMetrics.vue";
import {
  archiveAriaLabel,
  archiveToggleLabel,
  deleteAriaLabel,
  dragAriaLabel,
  dragTitle,
  hasRowActions,
  isArchived,
  reorderTargetOf,
  showStaleBadge,
  type ReorderKey
} from "./ledgerCard/ledgerCardModel";

/**
 * 账户卡片（#984 ledgers/index.vue 拆分）。
 * 从 index.vue 原样迁移：标题行/核心指标/关联负债的展示逻辑不变；
 * 点击进详情、删除按钮经事件上抛，路由与删除流程仍由父页面编排。
 *
 * #980 再拆一层：核心指标区（总资产 / 当日盈亏 / 持仓盈亏 / 关联负债）挪进
 * `ledgerCard/LedgerCardMetrics.vue`，本文件只留「标题行 + 归档徽标 + 事件上抛」；
 * 文案与 aria-label 的三元判断收进 `ledgerCard/ledgerCardModel.ts`。
 */
defineProps<{
  ledger: any;
  /** 持仓快照一致性待核对项数（#1133 §4 温柔提醒）：>0 时显示中性色角标，绝不阻断操作 */
  staleCount?: number;
  /**
   * 本卡在所属分组内的位置（0 起）与该组总数（#1841）。
   * 键盘重排的 aria-label 与 Home/End 目标位都靠它——没有这两个数，
   * 屏幕阅读器只能念「调整顺序」却念不出「当前第几位」。
   */
  index?: number;
  total?: number;
}>();

const emit = defineEmits<{
  /** 进入详情（卡片点击 / 回车） */
  open: [ledger: any];
  /** 删除按钮（已 stopPropagation，不触发卡片点击） */
  delete: [ledger: any];
  /** 归档 / 激活切换（已 stopPropagation） */
  toggleArchive: [ledger: any];
  /**
   * 键盘重排（#1841）：抓手 ↑/↓/Home/End 上抛目标下标，由页面调 reorderLedgers 落库。
   * 组件自己不落库——它不知道所属分组，跨组语义在页面层。
   */
  reorderKey: [payload: { ledger: any; to: number }];
}>();

function onReorderKey(
  ledger: any,
  key: ReorderKey,
  index?: number,
  total?: number
) {
  emit("reorderKey", { ledger, to: reorderTargetOf(key, index, total) });
}
</script>

<template>
  <div
    class="ledger-card"
    :class="{ 'is-archived': isArchived(ledger) }"
    role="button"
    tabindex="0"
    :aria-label="`查看账户 ${ledger.name}`"
    @click="emit('open', ledger)"
    @keydown.enter="emit('open', ledger)"
  >
    <!-- 标题行：名称 + 类型标签 + 行内操作（hover 卡片时浮现） -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2 min-w-0">
        <!-- 拖拽手柄：常驻低透明（暗示可拖拽），hover/focus 时高亮；点击/回车均 stop，避免触发卡片打开详情（#1083）
             键盘替代（#1841）：此前 tabindex="-1" 刻意不可聚焦，键盘用户无法排序（WCAG 2.1.1）。
             现在 ↑/↓ 移动一位、Home/End 移到首/尾，事件上抛给页面（落库与拖拽同一接口）。 -->
        <span
          class="drag-handle"
          role="button"
          tabindex="0"
          :aria-label="dragAriaLabel(ledger.name, index, total)"
          :title="dragTitle(ledger.name)"
          @click.stop
          @keydown.enter.stop
          @keydown.up.stop.prevent="onReorderKey(ledger, 'up', index, total)"
          @keydown.down.stop.prevent="
            onReorderKey(ledger, 'down', index, total)
          "
          @keydown.home.stop.prevent="
            onReorderKey(ledger, 'home', index, total)
          "
          @keydown.end.stop.prevent="onReorderKey(ledger, 'end', index, total)"
        >
          <!-- 卡片拖拽：四向「移动」双箭头，暗示单张卡片可上下/左右重排，与分组抓手（纵向三横线）明确区分 -->
          <svg
            class="drag-grip drag-grip--card"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M9 4 7 6l2 2" />
            <path d="M4 7h5" />
            <path d="m15 4 2 2-2 2" />
            <path d="M15 4h5" />
            <path d="M9 20l-2-2 2-2" />
            <path d="M4 17h5" />
            <path d="m15 20 2-2-2-2" />
            <path d="M15 20h5" />
          </svg>
        </span>
        <span
          class="font-semibold text-base truncate"
          :style="{ color: 'var(--text-primary)' }"
        >
          {{ ledger.name }}
        </span>
        <AssetTypeBadge :type="ledger.ledger_type" />
        <!-- 温柔提醒角标（#1133 §4）：中性信息色，不红不阻断；hover 提示建议核对 -->
        <el-tooltip
          v-if="showStaleBadge(staleCount)"
          content="持仓记录可能滞后，建议核对一下"
          placement="top"
          effect="light"
        >
          <span class="ledger-stale-badge" role="img" aria-label="持仓可能滞后">
            <IconifyIconOffline
              icon="ep:clock"
              class="ledger-stale-badge__icon"
            />
          </span>
        </el-tooltip>
      </div>
      <!-- 行内操作组：归档/激活 + 删除，作为整体靠右且彼此紧挨（text 图标按钮，统一轻盈风格） -->
      <div class="ledger-row-actions">
        <!-- 归档 / 激活切换：text 图标按钮，hover 显主题色；tooltip 说明用途 -->
        <el-tooltip
          v-if="hasRowActions(ledger)"
          :content="archiveToggleLabel(isArchived(ledger))"
          placement="top"
          effect="light"
        >
          <el-button
            text
            size="small"
            circle
            class="ledger-row-action"
            :aria-label="archiveAriaLabel(ledger.name, isArchived(ledger))"
            @click.stop="emit('toggleArchive', ledger)"
          >
            <IconifyIconOffline
              :icon="isArchived(ledger) ? 'ep:refresh-left' : 'ep:box'"
            />
          </el-button>
        </el-tooltip>
        <!-- 删除按钮：text 图标按钮，hover 显 danger 红（破坏性操作） -->
        <el-tooltip
          v-if="hasRowActions(ledger)"
          :content="'删除'"
          placement="top"
          effect="light"
        >
          <el-button
            type="danger"
            text
            size="small"
            circle
            class="ledger-row-action ledger-row-action--danger"
            :aria-label="deleteAriaLabel(ledger.name)"
            @click.stop="emit('delete', ledger)"
          >
            <IconifyIconOffline icon="ep:delete" />
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- 已归档徽标：灰化提示，数据仍参与收益计算 -->
    <div v-if="isArchived(ledger)" class="ledger-card__archived">
      <IconifyIconOffline icon="ep:box" class="mr-1" /> 已归档 · 数据仍计入收益
    </div>

    <!-- 核心指标 + 关联负债 -->
    <LedgerCardMetrics :ledger="ledger" />
  </div>
</template>

<style scoped>
.ledger-card {
  padding: var(--space-compact);
  cursor: pointer;
  outline: none; /* 焦点指示由 :focus-visible 环提供，勿移除 outline */
  background: var(--bg-card);
  border: var(--card-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.ledger-card:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.ledger-card:focus-visible {
  box-shadow: var(--focus-ring);
}

/* 拖拽中「被选中」的卡片：轻微放大 + 浮起，给用户明确反馈 */
.ledger-card--chosen {
  cursor: grabbing;
  box-shadow: var(--shadow-float);
  transform: scale(1.02);
}

.ledger-row-actions {
  display: flex;
  gap: 8px; /* 两个行内按钮固定紧挨，避免散开 */
  align-items: center;
}

/* 拖拽手柄：常驻低透明，既暗示「可拖拽」又不过度干扰；移动端需禁用默认触摸手势 */
.drag-handle {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin-right: 2px;
  color: var(--text-tertiary-ink);
  touch-action: none;
  cursor: grab;
  border-radius: var(--radius-sm);
  opacity: 0.55;
  transition:
    opacity 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}

.drag-handle:active {
  cursor: grabbing;
}

.ledger-card:hover .drag-handle,
.ledger-card:focus-within .drag-handle,
.drag-handle:hover {
  color: var(--brand-600);
  background: var(--bg-page);
  opacity: 1;
}

/* 卡片抓手：四向移动箭头，描边风格，自带内边距更透气 */
.drag-grip--card {
  padding: 1px;
}

/* 拖拽中占位「幽灵」元素的视觉态（sortablejs ghostClass） */
.ledger-card--ghost {
  box-shadow: var(--shadow-float);
  opacity: 0.4;
  transform: scale(1.02);
}

.ledger-row-action {
  /* text 图标按钮常显为中性灰图标，视觉权重统一 */
  color: var(--text-tertiary-ink);
  opacity: 0;
  transition:
    opacity 0.2s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}

/* 两个行内按钮 hover 效果统一：图标变色 + 浅背景（用父级前缀提权，确保盖过 EP 默认 is-text:hover） */
.ledger-row-actions .ledger-row-action:not(.ledger-row-action--danger):hover,
.ledger-row-actions
  .ledger-row-action:not(.ledger-row-action--danger):focus-visible {
  color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}

.ledger-row-actions .ledger-row-action--danger:hover,
.ledger-row-actions .ledger-row-action--danger:focus-visible {
  color: var(--color-danger);
  background-color: var(--el-color-danger-light-9);
}

.ledger-card:hover .ledger-row-action,
.ledger-card:focus-within .ledger-row-action,
.ledger-row-action:focus-visible {
  opacity: 1;
}

/* ===== 归档态：灰化但保留完整信息（数据仍参与收益计算） ===== */
.ledger-card.is-archived {
  background: var(--bg-soft);
  border-style: dashed;
  opacity: 0.62;
}

.ledger-card.is-archived:hover {
  opacity: 0.85;
}

/* 温柔提醒角标（#1133 §4）：中性信息色（非涨跌色 / 非危险红），轻量、不制造心理压力 */
.ledger-stale-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--el-color-info);
  background: var(--el-color-info-light-9);
  border-radius: var(--radius-pill);
}

.ledger-stale-badge__icon {
  font-size: var(--text-label);
}

.ledger-card__archived {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  margin-bottom: var(--space-2);
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
  background: var(--bg-page);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
}

/* 触屏设备无 hover 态，直接常显，避免删除入口不可达 */

/* ── 触屏 / 动效偏好适配 ──
   ⚠️ 以下三块原先都排在基础声明**之前**，被同特异性、后写的规则压掉（2026-09-18 修复，见 #1576 台账）。 */
@media (hover: none) {
  .ledger-row-action {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ledger-card,
  .ledger-row-action {
    transition: none;
  }

  .ledger-card:hover {
    transform: none;
  }
}

@media (hover: none) {
  .ledger-card.is-archived {
    opacity: 0.7;
  }
}
</style>
