<script setup lang="ts">
import type { LedgerLike } from "./ledgerTypes";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { TodayPnlGroup } from "@/api/summary";
import LedgerCardMetrics from "./ledgerCard/LedgerCardMetrics.vue";
import LedgerCardHead from "./ledgerCard/LedgerCardHead.vue";
import { isArchived } from "./ledgerCard/ledgerCardModel";

/**
 * 账户卡片（#984 / #980 拆分，2026-11-21 再拆标题行）：
 * 本文件只剩卡片壳 + 归档徽标 + 指标区编排。
 * 标题行（拖拽 / 徽标 / 归属 / 归档 / 删除）在 `ledgerCard/LedgerCardHead.vue`，
 * 指标在 `ledgerCard/LedgerCardMetrics.vue`，文案与 aria 判断在 `ledgerCardModel.ts`。
 * 路由与删除流程由父页面编排，卡片不自行取数。
 */
defineOptions({ name: "LedgerCard" });

defineProps<{
  ledger: LedgerLike;
  /** 持仓快照一致性待核对项数（#1133 §4 温柔提醒）：>0 时显示中性色角标，绝不阻断操作 */
  staleCount?: number;
  /** 当日估值（`dimension=ledger` 的分组行）；null = 该账户无可估值持仓 */
  todayPnl?: TodayPnlGroup | null;
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
  open: [ledger: LedgerLike];
  /** 删除按钮（已 stopPropagation，不触发卡片点击） */
  delete: [ledger: LedgerLike];
  /** 归档 / 激活切换（已 stopPropagation） */
  toggleArchive: [ledger: LedgerLike];
  /**
   * 键盘重排（#1841）：抓手 ↑/↓/Home/End 上抛目标下标，由页面调 reorderLedgers 落库。
   * 组件自己不落库——它不知道所属分组，跨组语义在页面层。
   */
  reorderKey: [payload: { ledger: LedgerLike; to: number }];
}>();
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
    <LedgerCardHead
      :ledger="ledger"
      :stale-count="staleCount"
      :index="index"
      :total="total"
      @delete="l => emit('delete', l)"
      @toggle-archive="l => emit('toggleArchive', l)"
      @reorder-key="payload => emit('reorderKey', payload)"
    />

    <!-- 已归档徽标：灰化提示，数据仍参与收益计算 -->
    <div v-if="isArchived(ledger)" class="ledger-card__archived">
      <IconifyIconOffline icon="ep:box" class="mr-1" /> 已归档 · 数据仍计入收益
    </div>

    <!-- 核心指标 + 关联负债 -->
    <LedgerCardMetrics :ledger="ledger" :today-pnl="todayPnl" />
  </div>
</template>

<style scoped>
.ledger-card {
  /* 24px：与上方概览卡的 CardBlock 内边距一致——两张卡上下相邻，内文左缘
     必须落在同一条竖线上；原先 16px 让账户卡的文字比概览卡左移 8px。 */
  padding: var(--space-standard);
  cursor: pointer;
  outline: none; /* 焦点指示由 :focus-visible 环提供，勿移除 outline */
  background: var(--bg-card);
  border: var(--card-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;

  /* 入场：首次出现时轻微上浮 + 淡入，按组内序号错峰（最多 180ms）。
     fill-mode 必须是 `backwards`（只负责延迟期），不能用 `both/forwards`——
     否则动画末帧的 transform 会持续生效，把 :hover 的上浮永久压掉。
     重排 / 归档刷新走同一批 key，不会重播。 */
  animation: ledger-card-in 0.3s ease-out backwards;
  animation-delay: calc(var(--card-index, 0) * 30ms);
}

@keyframes ledger-card-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
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

/* 拖拽中占位「幽灵」元素的视觉态（sortablejs ghostClass） */
.ledger-card--ghost {
  box-shadow: var(--shadow-float);
  opacity: 0.4;
  transform: scale(1.02);
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

@media (prefers-reduced-motion: reduce) {
  .ledger-card {
    transition: none;
    animation: none;
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
