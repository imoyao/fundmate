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
}>();
</script>

<template>
  <div
    class="ledger-card"
    role="button"
    tabindex="0"
    :aria-label="`查看账户 ${ledger.name}`"
    @click="emit('open', ledger)"
    @keydown.enter="emit('open', ledger)"
  >
    <!-- 标题行：名称 + 类型标签 + 行内操作（hover 卡片时浮现） -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2 min-w-0">
        <span
          class="font-semibold text-base truncate"
          :style="{ color: 'var(--text-primary)' }"
        >
          {{ ledger.name }}
        </span>
        <AssetTypeBadge :type="ledger.ledger_type" />
      </div>
      <!-- 删除按钮：幽灵态 + hover 浮现（design.md「行内操作交互规范」） -->
      <el-button
        v-if="typeof ledger.id === 'number'"
        type="danger"
        plain
        size="small"
        circle
        class="ledger-row-action"
        :aria-label="`删除账户 ${ledger.name}`"
        @click.stop="emit('delete', ledger)"
      >
        <IconifyIconOffline icon="ep:delete" />
      </el-button>
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
