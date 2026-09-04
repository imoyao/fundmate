<script setup lang="ts">
import { ElMessageBox } from "element-plus";
import { REFRESH_INTERVAL_OPTIONS } from "@/composables/useRealtimeQuotes";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { getTypeLabel } from "@/constants/assetType";
import { pricePrecision } from "@/utils/pricePrecision";
import { formatDateTime } from "@/utils/date";

/**
 * 探市·观察列表（#984 explore/index.vue 拆分）。
 * 纯展示组件：汇总条 + 表格；数据经 props 注入，
 * 删除/深度分析跳转/刷新/档位切换经事件上抛由父页面编排。
 */
defineProps<{
  rows: any[];
  loading: boolean;
  totalCount: number;
  /** true = 未填成本份额的纯观察模式（隐藏盈亏列） */
  isPureObservationMode: boolean;
  summary?: {
    totalMarketValue: number;
    totalPnl: number;
  } | null;
  statusClass: string;
  statusText: string;
  refreshInterval: number;
  lastUpdateTime: string;
}>();

interface ExploreRow {
  symbol: string;
  type: string;
  name: string;
  id?: string | number;
}
const emit = defineEmits<{
  remove: [id: string];
  jump: [row: any, command: string];
  refresh: [];
  "interval-change": [value: number];
  favorite: [row: ExploreRow];
}>();

function handleRemoveConfirm(id: string) {
  ElMessageBox.confirm("确定从观察列表中移除该资产吗？", "提示", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning"
  })
    .then(() => emit("remove", id))
    .catch(() => {});
}

// 深度分析外部工具清单（基金/ETF 多一个天天基金）
const getAvailableTools = (type: string) => {
  const tools = [
    { key: "xueqiu", label: "雪球社区" },
    { key: "eastmoney", label: "东方财富" }
  ];
  if (type === "fund" || type === "etf") {
    tools.push({ key: "tiantian", label: "天天基金" });
  }
  return tools;
};
</script>

<template>
  <section class="watchlist-section">
    <div class="summary-bar">
      <div class="summary-left">
        <span class="summary-count">共 {{ totalCount }} 项</span>
        <template v-if="!isPureObservationMode && summary">
          <span class="summary-divider">|</span>
          <span class="summary-value"
            >总市值
            <MoneyDisplay :value="summary.totalMarketValue" :show-sign="false"
          /></span>
          <span class="summary-divider">|</span>
          <span class="summary-pnl"
            >盈亏 <RiseFallText :value="summary.totalPnl" suffix=""
          /></span>
        </template>
        <span v-if="isPureObservationMode" class="summary-hint"
          >输入成本与份额后可查看持仓盈亏</span
        >
      </div>
      <div class="summary-right">
        <span class="status-indicator">
          <span class="status-dot" :class="statusClass" />{{ statusText }}
        </span>
        <el-select
          :model-value="refreshInterval"
          size="small"
          class="refresh-interval-select"
          @change="emit('interval-change', $event as number)"
        >
          <el-option
            v-for="s in REFRESH_INTERVAL_OPTIONS"
            :key="s"
            :label="`${s}s 刷新`"
            :value="s"
          />
        </el-select>
        <span v-if="lastUpdateTime" class="update-time"
          >更新: {{ formatDateTime(lastUpdateTime) }}</span
        >
        <el-button size="small" @click="emit('refresh')">刷新</el-button>
      </div>
    </div>

    <!-- 表格视觉基线统一在 src/style/el-table.css 维护，勿在本页 :deep 覆盖 -->
    <el-table
      v-loading="loading"
      :data="rows"
      border
      style="width: 100%"
      empty-text="暂无观察资产，添加你关注的标的开始研究"
    >
      <el-table-column label="产品" min-width="180">
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name"
            :symbol="row.symbol"
            :type-label="getTypeLabel(row.type)"
          />
        </template>
      </el-table-column>

      <el-table-column label="最新价" width="120" align="right">
        <template #default="{ row }"
          ><MoneyDisplay
            :value="row.price"
            :show-sign="false"
            :precision="pricePrecision(row.type)"
        /></template>
      </el-table-column>

      <el-table-column label="涨跌幅" width="110" align="right">
        <template #default="{ row }"
          ><RiseFallText :value="row.changePct"
        /></template>
      </el-table-column>

      <el-table-column
        v-if="!isPureObservationMode"
        label="当日盈亏"
        width="130"
        align="right"
      >
        <template #default="{ row }"
          ><MoneyDisplay :value="row.pnl ?? 0" :show-sign="true"
        /></template>
      </el-table-column>

      <el-table-column
        v-if="!isPureObservationMode"
        label="持仓收益"
        width="130"
        align="right"
      >
        <template #default="{ row }"
          ><MoneyDisplay :value="row.positionPnl ?? 0" :show-sign="true"
        /></template>
      </el-table-column>

      <el-table-column label="深度分析" width="120" align="center">
        <template #default="{ row }">
          <el-dropdown
            @command="(command: string) => emit('jump', row, command)"
          >
            <el-button size="small" type="primary" plain>分析 ▼</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="tool in getAvailableTools(row.type)"
                  :key="tool.key"
                  :command="tool.key"
                >
                  {{ tool.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button
            link
            size="small"
            type="primary"
            @click="emit('favorite', row as ExploreRow)"
            >收藏</el-button>
          <el-button
            link
            size="small"
            style="color: var(--text-tertiary)"
            @click="handleRemoveConfirm(row.id)"
            >删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style lang="scss" scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

/* ============================================================
   观察列表样式（自 index.vue 随组件迁移，#984）
   ============================================================ */
.watchlist-section {
  max-width: 1280px;
  padding: 0 24px 24px;
  margin: 0 auto;
}

.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 16px;

  .summary-left {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }

  .summary-count {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .summary-divider {
    color: var(--border-default);
  }

  .summary-value {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .summary-pnl {
    font-size: 14px;
  }

  .summary-hint {
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .summary-right {
    display: flex;
    gap: 12px;
    align-items: center;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  .refresh-interval-select {
    width: 96px;
  }

  .status-indicator {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;

    &.status-trading {
      background: var(--color-rise);
      animation: pulse 1.5s infinite;
    }

    &.status-closed {
      background: var(--text-tertiary);
    }

    &.status-error {
      background: var(--color-danger-system);
      animation: pulse 1s infinite;
    }

    &.status-idle {
      background: var(--text-disabled);
    }
  }
}
</style>
