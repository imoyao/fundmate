<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 账户卡片（#984 ledgers/index.vue 拆分）。
 * 从 index.vue 原样迁移：标题行/核心指标/关联负债的展示逻辑不变；
 * 点击进详情、删除按钮经事件上抛，路由与删除流程仍由父页面编排。
 */
defineProps<{
  ledger: any;
}>();

const emit = defineEmits<{
  /** 进入详情（卡片点击 / 回车） */
  open: [ledger: any];
  /** 删除按钮（已 stopPropagation，不触发卡片点击） */
  delete: [ledger: any];
  /** 归档 / 激活切换（已 stopPropagation） */
  toggleArchive: [ledger: any];
}>();
</script>

<template>
  <div
    class="ledger-card"
    :class="{ 'is-archived': ledger.is_active === false }"
    role="button"
    tabindex="0"
    :aria-label="`查看账户 ${ledger.name}`"
    @click="emit('open', ledger)"
    @keydown.enter="emit('open', ledger)"
  >
    <!-- 标题行：名称 + 类型标签 + 行内操作（hover 卡片时浮现） -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2 min-w-0">
        <!-- 拖拽手柄：常驻低透明（暗示可拖拽），hover/focus 时高亮；点击/回车均 stop，避免触发卡片打开详情（#1083） -->
        <span
          class="drag-handle"
          role="button"
          tabindex="-1"
          :title="`拖拽排序：${ledger.name}`"
          @click.stop
          @keydown.enter.stop
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
      </div>
      <!-- 行内操作组：归档/激活 + 删除，作为整体靠右且彼此紧挨（text 图标按钮，统一轻盈风格） -->
      <div class="ledger-row-actions">
        <!-- 归档 / 激活切换：text 图标按钮，hover 显主题色；tooltip 说明用途 -->
        <el-tooltip
          v-if="typeof ledger.id === 'number'"
          :content="ledger.is_active === false ? '激活' : '归档'"
          placement="top"
          effect="light"
        >
          <el-button
            text
            size="small"
            circle
            class="ledger-row-action"
            :aria-label="
              (ledger.is_active === false ? '激活账户 ' : '归档账户 ') +
              ledger.name
            "
            @click.stop="emit('toggleArchive', ledger)"
          >
            <IconifyIconOffline
              :icon="ledger.is_active === false ? 'ep:refresh-left' : 'ep:box'"
            />
          </el-button>
        </el-tooltip>
        <!-- 删除按钮：text 图标按钮，hover 显 danger 红（破坏性操作） -->
        <el-tooltip
          v-if="typeof ledger.id === 'number'"
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
            :aria-label="`删除账户 ${ledger.name}`"
            @click.stop="emit('delete', ledger)"
          >
            <IconifyIconOffline icon="ep:delete" />
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- 已归档徽标：灰化提示，数据仍参与收益计算 -->
    <div v-if="ledger.is_active === false" class="ledger-card__archived">
      <IconifyIconOffline icon="ep:box" class="mr-1" /> 已归档 · 数据仍计入收益
    </div>

    <!-- 核心指标：左右两列 flex（总资产为左侧大数字锚点，右侧两指标独立竖排，
         避免大数字撑高整行把右侧指标挤到下方） -->
    <div class="ledger-metrics">
      <div class="metric metric--main">
        <span class="metric-label" :style="{ color: 'var(--text-tertiary)' }"
          >总资产</span
        >
        <span class="metric-value" :style="{ color: 'var(--text-primary)' }">
          <MoneyDisplay
            :value="ledger.total_market_value || 0"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
        </span>
      </div>
      <!-- 右侧两指标：独立竖排容器，垂直居中于卡片高度，互不挤压 -->
      <div class="metric-side">
        <!-- 当日盈亏：暂无当日行情数据，保留占位符 -->
        <div class="metric">
          <span class="metric-label" :style="{ color: 'var(--text-tertiary)' }"
            >当日盈亏</span
          >
          <span class="metric-value" :style="{ color: 'var(--text-tertiary)' }"
            >--</span
          >
        </div>
        <!-- 持仓盈亏：银行显示活期余额、实物显示估值项数 -->
        <div class="metric">
          <span class="metric-label" :style="{ color: 'var(--text-tertiary)' }">
            {{
              ledger.ledger_type === "bank"
                ? "活期余额"
                : ledger.ledger_type === "property"
                  ? "估值"
                  : "持仓盈亏"
            }}
          </span>
          <template
            v-if="
              ledger.ledger_type === 'bank' &&
              ledger.cash_balance !== undefined &&
              ledger.cash_balance !== null
            "
          >
            <span
              class="metric-value"
              :style="{ color: 'var(--text-secondary)' }"
            >
              <MoneyDisplay
                :value="ledger.cash_balance"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </span>
          </template>
          <template v-else-if="ledger.ledger_type === 'property'">
            <span
              class="metric-value"
              :style="{ color: 'var(--text-secondary)' }"
            >
              {{ ledger.position_count || 0 }} 项
            </span>
          </template>
          <span v-else class="metric-value">
            <!-- 盈亏数字走 MoneyDisplay 自动涨红跌绿 -->
            <MoneyDisplay :value="ledger.pnl || 0" size="sm" />
          </span>
        </div>
      </div>
    </div>

    <!-- 关联负债（仅银行账户且存在房贷时显示；负债属中性信息，用 text-secondary） -->
    <div
      v-if="ledger.ledger_type === 'bank' && ledger.linked_liability > 0"
      class="ledger-liability"
    >
      <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
        >关联负债</span
      >
      <span
        class="text-xs font-medium"
        :style="{ color: 'var(--text-secondary)' }"
      >
        <MoneyDisplay
          :value="-ledger.linked_liability"
          :auto-color="false"
          size="xs"
        />
      </span>
    </div>
  </div>
</template>

<style scoped>
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

/* ===== 核心指标：左右两列 flex（总资产大数字锚点 + 右侧两指标独立竖排） ===== */
.ledger-metrics {
  display: flex;
  gap: var(--space-3);
  align-items: stretch;
}

.metric--main {
  display: flex;
  flex: 1.25;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
  min-width: 0;
  overflow-wrap: anywhere;
}

.metric-side {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-2);
  justify-content: center;
  min-width: 0;
}

.metric-label {
  display: block;
  font-size: var(--text-label, 13px);
  line-height: 18px;
}

.metric-value {
  display: block;
  font-size: var(--text-small, 14px);
  font-variant-numeric: tabular-nums;
  line-height: 22px;
}

.ledger-liability {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  margin-top: var(--space-3);
  font-variant-numeric: tabular-nums;
  border-top: 1px solid var(--border-subtle);
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
  color: var(--text-tertiary);
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
  color: var(--text-tertiary);
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
  color: var(--el-color-danger);
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

.ledger-card__archived {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  margin-bottom: var(--space-2);
  font-size: 12px;
  line-height: 18px;
  color: var(--text-tertiary);
  background: var(--bg-page);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
}

/* 触屏设备无 hover 态，直接常显，避免删除入口不可达 */
</style>
