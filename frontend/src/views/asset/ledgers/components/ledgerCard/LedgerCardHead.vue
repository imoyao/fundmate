<script setup lang="ts">
import type { LedgerLike } from "../ledgerTypes";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
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
} from "./ledgerCardModel";

/**
 * 账户卡片标题行（2026-11-21 从 LedgerCard 拆出）：
 * 拖拽抓手 + 名称 + 类型徽标 + 归属成员 + 滞后角标 + 行内操作（归档 / 删除）。
 *
 * 拆出来的原因不是「文件行数」本身，而是这一行承载了**四种交互**（拖拽排序、
 * 打开详情、归档、删除），与下方的只读指标区混在一个文件里，改排版时会互相牵连。
 * 事件一律上抛给 LedgerCard 再转给页面，组件自己不碰数据。
 */
defineOptions({ name: "LedgerCardHead" });

const props = defineProps<{
  ledger: LedgerLike;
  /** 持仓快照一致性待核对项数（#1133 §4 温柔提醒）：>0 时显示中性色角标 */
  staleCount?: number;
  /** 本卡在所属分组内的位置（0 起）与该组总数（#1841） */
  index?: number;
  total?: number;
}>();

const emit = defineEmits<{
  delete: [ledger: LedgerLike];
  toggleArchive: [ledger: LedgerLike];
  reorderKey: [payload: { ledger: LedgerLike; to: number }];
}>();

function onReorderKey(
  ledger: LedgerLike,
  key: ReorderKey,
  index?: number,
  total?: number
) {
  emit("reorderKey", { ledger, to: reorderTargetOf(key, index, total) });
}
</script>

<template>
  <div class="ledger-card__head">
    <div class="ledger-card__identity">
      <!-- 拖拽手柄：常驻低透明（暗示可拖拽），hover/focus 时高亮；点击/回车均 stop，
           避免触发卡片打开详情（#1083）。键盘替代（#1841）：↑/↓ 移动一位、
           Home/End 移到首/尾，事件上抛给页面（落库与拖拽同一接口）。 -->
      <span
        class="drag-handle"
        role="button"
        tabindex="0"
        :aria-label="dragAriaLabel(ledger.name, index, total)"
        :title="dragTitle(ledger.name)"
        @click.stop
        @keydown.enter.stop
        @keydown.up.stop.prevent="onReorderKey(ledger, 'up', index, total)"
        @keydown.down.stop.prevent="onReorderKey(ledger, 'down', index, total)"
        @keydown.home.stop.prevent="onReorderKey(ledger, 'home', index, total)"
        @keydown.end.stop.prevent="onReorderKey(ledger, 'end', index, total)"
      >
        <!-- 卡片拖拽：四向「移动」双箭头，暗示单张卡片可上下/左右重排，
             与分组抓手（纵向三横线）明确区分 -->
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
      <span class="ledger-card__name">{{ ledger.name }}</span>
      <!-- 类型标签读 channel_category（用户可见渠道类别），不读 ledger_type：
           后者是内部计算口径键，且编辑时不可变（409），拿它当标签会让用户
           永远改不掉错误显示（微众银行曾长期在「银行」组里挂「基」徽标）。 -->
      <AssetTypeBadge :channel-category="ledger.channel_category" />
      <!-- 归属家庭成员（#1173）：只在有归属时显示——「家庭共有」是常态，
           占位反而让每个卡片都多一个无信息量的标签 -->
      <el-tooltip
        v-if="ledger.owner_member_id"
        :content="`归属：${ledger.owner_member_name || '未知成员'}`"
        placement="top"
        effect="light"
      >
        <el-tag
          size="small"
          type="info"
          effect="plain"
          class="ledger-owner-tag"
        >
          <IconifyIconOffline icon="ep:user" class="ledger-owner-tag__icon" />
          {{ ledger.owner_member_name || "未知成员" }}
        </el-tag>
      </el-tooltip>
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

    <!-- 行内操作组：归档/激活 + 删除，作为整体靠右且彼此紧挨（text 图标按钮） -->
    <div class="ledger-row-actions">
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
      <el-tooltip
        v-if="hasRowActions(ledger)"
        content="删除"
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
</template>

<style scoped>
.ledger-card__head {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.ledger-card__identity {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.ledger-card__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
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

.ledger-row-actions {
  display: flex;
  flex: none;
  gap: 8px;
  align-items: center;
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

/* 两个行内按钮 hover 效果统一：图标变色 + 浅背景
   （用父级前缀提权，确保盖过 EP 默认 is-text:hover） */
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

/* 温柔提醒角标（#1133 §4）：中性信息色（非涨跌色 / 非危险红），轻量、不制造心理压力 */
.ledger-stale-badge {
  display: inline-flex;
  flex: none;
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

/* 触屏设备无 hover 态，操作按钮直接常显，避免删除入口不可达 */
@media (hover: none) {
  .ledger-row-action {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .drag-handle,
  .ledger-row-action {
    transition: none;
  }
}
</style>
