<!--
  WatchlistQuickViewDrawer · 自选行「速览」抽屉（#1285）

  设计文档「行内交互：抽屉 vs 详情页」两级模型的第一步：
  行点击 → 抽屉（速览）→ 抽屉内「查看详情」→ 完整详情页。

  本版本为**速览版**：展示当前可得的通用字段（行情 / 持有 / 信息 / 备注）。
  品种专属维度（指数估值、可转债条款、投顾持仓等）待数据底座落地后增量补充；
  详情页入口**预留且禁用**（详情页后期实现），避免与「行点击」争抢语义。

  可持有品类判定与列配置层一致：index / manager / portfolio 不展示「持有」区。
-->
<template>
  <el-drawer
    v-model="visible"
    title="速览"
    size="420px"
    direction="rtl"
    destroy-on-close
  >
    <div v-if="item" class="wqv">
      <!-- 头部：名称 / 代码 / 类型 / 组合分层信息 -->
      <div class="wqv-head">
        <div class="wqv-name" :title="item.display_name || item.symbol">
          {{ item.display_name || item.symbol }}
        </div>
        <div class="wqv-meta">
          <span v-if="!isComposite && item.symbol" class="wqv-code">
            {{ item.symbol }}
          </span>
          <span v-if="item.type_label" class="wqv-type">
            {{ item.type_label }}
          </span>
        </div>
        <div v-if="compositeMeta" class="wqv-meta">{{ compositeMeta }}</div>
      </div>

      <!-- 行情 -->
      <section class="wqv-sec">
        <h4 class="wqv-sec__title">行情</h4>
        <dl class="wqv-grid">
          <div class="wqv-cell">
            <dt class="wqv-label">最新价</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="hasPrice"
                :value="item.current_price as number"
                :precision="precision"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">涨跌幅</dt>
            <dd class="wqv-value">
              <RiseFallText
                v-if="hasChange"
                :value="item.change_pct as number"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- 持有（仅可持有品类） -->
      <section v-if="isHoldable" class="wqv-sec">
        <h4 class="wqv-sec__title">持有</h4>
        <dl class="wqv-grid">
          <div class="wqv-cell">
            <dt class="wqv-label">持有数量</dt>
            <dd class="wqv-value">
              {{ item.holding_quantity != null ? item.holding_quantity : "—" }}
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">持仓市值</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="item.position_market_value != null"
                :value="item.position_market_value"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">成本价</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="item.holding_cost_price != null"
                :value="item.holding_cost_price"
                :precision="precision"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
          <div class="wqv-cell">
            <dt class="wqv-label">持仓收益</dt>
            <dd class="wqv-value">
              <MoneyDisplay
                v-if="item.holding_pnl != null"
                :value="item.holding_pnl"
                size="sm"
              />
              <span v-else class="wqv-empty">—</span>
            </dd>
          </div>
        </dl>
      </section>

      <!-- 信息 -->
      <section class="wqv-sec">
        <h4 class="wqv-sec__title">信息</h4>
        <dl class="wqv-list">
          <div class="wqv-row">
            <dt class="wqv-label">添加自选日</dt>
            <dd class="wqv-value">
              {{ item.created_at ? formatDate(item.created_at) : "—" }}
            </dd>
          </div>
          <div class="wqv-row">
            <dt class="wqv-label">所属分组</dt>
            <dd class="wqv-value">{{ groupText }}</dd>
          </div>
          <div class="wqv-row">
            <dt class="wqv-label">标签</dt>
            <dd class="wqv-value">{{ tagText }}</dd>
          </div>
        </dl>
      </section>

      <!-- 备注（可编辑） -->
      <section class="wqv-sec">
        <div class="wqv-sec__head">
          <h4 class="wqv-sec__title">备注</h4>
          <el-button text size="small" @click="emit('edit-notes', item)">
            编辑
          </el-button>
        </div>
        <p v-if="item.notes" class="wqv-notes">{{ item.notes }}</p>
        <p v-else class="wqv-empty">暂无备注</p>
      </section>

      <!-- 详情页入口（预留，详情页后期实现） -->
      <div class="wqv-footer">
        <el-button disabled>查看详情</el-button>
        <span class="wqv-hint">详情页开发中</span>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";
import type { WatchlistItem } from "@/api/watchlist";

const props = defineProps<{
  modelValue: boolean;
  item: WatchlistItem | null;
  /** 全部标签（用于 tag_ids → 名称映射，与表格渲染同一份数据） */
  allTags?: { id: number; name: string; color?: string | null }[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  /** 点击「编辑」→ 由页面打开备注编辑弹窗（复用 #1285 的 NotesEditorDialog） */
  "edit-notes": [item: WatchlistItem];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

/** 非交易实体（组合 / 经理）：不展示代码、不展示「持有」区 */
const COMPOSITE_TYPES = new Set(["manager", "portfolio"]);
/** 不可持有品类：与 columnDefs.TRADABLE_TYPES 互补 */
const NON_HOLDABLE_TYPES = new Set(["index", "manager", "portfolio"]);

const assetType = computed(() => (props.item?.asset_type || "").toLowerCase());
const isComposite = computed(() => COMPOSITE_TYPES.has(assetType.value));
const isHoldable = computed(() => !NON_HOLDABLE_TYPES.has(assetType.value));
const precision = computed(() => pricePrecision(props.item?.asset_type ?? ""));

const hasPrice = computed(
  () => props.item?.current_price != null && props.item.current_price !== 0
);
const hasChange = computed(() => props.item?.change_pct != null);

/** 组合类标的的分层信息（平台 · 主理人 · 策略；经理为所属公司） */
const compositeMeta = computed(() => {
  const it = props.item;
  if (!it) return "";
  if (assetType.value === "portfolio") {
    return [it.advisor_platform, it.advisor_host, it.advisor_strategy_type]
      .filter(Boolean)
      .join(" · ");
  }
  if (assetType.value === "manager") {
    return it.manager_company || "";
  }
  return "";
});

const groupText = computed(() => {
  const names = props.item?.group_names ?? [];
  return names.length ? names.join("、") : "—";
});

const tagText = computed(() => {
  const ids = props.item?.tag_ids ?? [];
  const names = ids
    .map(id => props.allTags?.find(t => t.id === id)?.name)
    .filter((n): n is string => !!n);
  return names.length ? names.join("、") : "—";
});
</script>

<style scoped>
.wqv {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 16px);
}

.wqv-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wqv-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.wqv-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

.wqv-sec {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wqv-sec__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.wqv-sec__title {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.wqv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  margin: 0;
}

.wqv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
}

.wqv-cell,
.wqv-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.wqv-row {
  justify-content: space-between;
}

.wqv-label {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.wqv-value {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  text-align: right;
}

.wqv-empty {
  color: var(--text-disabled);
}

.wqv-notes {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.wqv-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: var(--space-2, 8px);
  border-top: 1px solid var(--border-light);
}

.wqv-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
