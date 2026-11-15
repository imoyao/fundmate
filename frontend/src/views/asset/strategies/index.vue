<template>
  <div
    class="strategies-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-6" data-region="strategy-header">
      <div class="flex items-center gap-2">
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          策略视图
        </h2>
        <!-- 口径说明不常驻：原先标题副标与橙色横幅把「不是独立组合收益率」
             说了两遍。收进标题 ⓘ 按需展开，信息不丢，首屏少两行噪音。 -->
        <el-tooltip placement="top" :popper-class="RICH_TIP_CLASS">
          <span
            class="strategy-scope__info"
            role="img"
            tabindex="0"
            aria-label="策略视图口径"
            data-action="strategy-scope-info"
          >
            <IconifyIconOffline icon="ep:info-filled" aria-hidden="true" />
          </span>
          <template #content>
            <p v-for="(line, i) in STRATEGY_SCOPE_TIP" :key="i">{{ line }}</p>
          </template>
        </el-tooltip>
      </div>
    </div>

    <!-- 加载状态 -->
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <p>加载中...</p>
    </div>

    <template v-else>
      <!-- 顶部操作栏 -->
      <div class="flex justify-between items-center mb-6">
        <StrategySummaryCards
          :total-holdings="totalHoldings"
          :tag-count="allTags.length"
          :total-market-value="totalMarketValue"
          :total-pnl="totalPnl"
        />
        <div class="flex gap-3 items-center">
          <!-- 盈亏双线（#1104）：口径说明 + 实时估值开关 -->
          <el-tooltip :content="PNL_DUAL_SCOPE_TIP" placement="top">
            <span
              class="text-xs"
              :style="{ color: 'var(--text-tertiary-ink)', cursor: 'help' }"
              >盈亏口径</span
            >
          </el-tooltip>
          <RealtimeEstimateToggle
            :enabled="estimateEnabled"
            :status="estimateStatus"
            :last-update-time="estimateUpdatedAt"
            :text="estimateToggleText"
            @toggle="estimateQuotes.toggle"
          />
          <el-button @click="tagManagerVisible = true">
            <IconifyIconOffline icon="ep:setting" class="mr-1" /> 管理标签
          </el-button>
        </div>
      </div>

      <!-- 分组列表（每组自带组内分页，页码是子组件本地状态） -->
      <StrategyGroupSection
        v-for="group in strategyGroups"
        :key="group.tag"
        :group="group"
        :all-tags="allTags"
        :page-size="groupPageSize"
        :create-tag="createTagForRow"
        :estimated-pnl="estimatedPnl"
        :estimate-hint="estimateHint"
        @unbind="p => unbindTag(p.positionId, p.tag)"
        @update-tags="p => updateTags(p.positionId, p.tags)"
      />

      <!-- 无数据时 -->
      <div
        v-if="strategyGroups.length === 0"
        class="text-center py-20"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        <IconifyIconOffline
          icon="ep:collection"
          class="text-5xl mb-3 opacity-30"
        />
        <p class="text-lg">暂无持仓，请先导入或录入交易数据</p>
      </div>
    </template>

    <!-- 标签管理对话框 -->
    <StrategyTagManagerDialog
      v-model="tagManagerVisible"
      :tags="allTags"
      :create-tag="createGlobalTag"
      @delete="deleteGlobalTag"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PnlDualLine from "@/components/PnlDualLine/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import {
  confirmedPnl,
  PNL_DUAL_SCOPE_TIP,
  usePositionValuation
} from "@/composables/usePositionValuation";
import { RICH_TIP_CLASS } from "@/utils/tooltipText";
import { getStrategyOverview } from "@/api/strategy";
import StrategySummaryCards from "./strategyView/StrategySummaryCards.vue";
import StrategyGroupSection from "./strategyView/StrategyGroupSection.vue";
import StrategyTagCell from "./strategyView/StrategyTagCell.vue";
import StrategyTagManagerDialog from "./strategyView/StrategyTagManagerDialog.vue";
import { useStrategyTags } from "./strategyView/useStrategyTags";
import {
  type EnrichedHolding,
  applyTags,
  buildStrategyGroups,
  enrichHoldings,
  sumMarketValue,
  sumPnl
} from "./strategyView/strategyViewModel";

/**
 * 策略视图（/asset/strategies）。
 *
 * 按标签分组看持仓表现：一只持仓可带多个标签 ⇒ **会同时出现在多个组里**（多对多），
 * 所以各组市值/盈亏相加不等于顶部汇总——顶部汇总取原始持仓，不取分组结果。
 *
 * #980 拆分后本文件只做编排：
 * - 富化 / 分组 / 分组分页 / 标签 diff 都在 `strategyView/strategyViewModel.ts`（纯函数）
 * - 标签的增删改在 `strategyView/useStrategyTags.ts`（逐项收集失败，不空 catch）
 * - 四张汇总卡、标签单元格、标签管理对话框各自成组件
 */
defineOptions({ name: "Strategies" });

/** 标题 ⓘ 的口径：原副标与橙色横幅两处同义文案合并，按句分行 */
const STRATEGY_SCOPE_TIP = [
  "按投资风格标签分组查看持仓表现，不参与组合收益率计算。",
  "策略视图展示的是持仓风格分析，不是独立投资组合的收益率。若需独立计算收益率，请创建投资组合并关联账户。"
];

const loading = ref(true);
const rawHoldings = ref<EnrichedHolding[]>([]);
const tagManagerVisible = ref(false);

/**
 * 盈亏双线（#1104）：估值接线。
 *
 * 传 **`rawHoldings`（原始持仓，每只一份）** 而非 `strategyGroups`：
 * 策略分组是「一只持仓按标签复制进多个组」的多对多结构，传分组结果会让同一 symbol
 * 出现多个副本，估值引擎按 symbol 查回时命中哪一份不确定。
 */
const {
  estimatedPnl,
  estimateHint,
  estimateEnabled,
  estimateStatus,
  estimateUpdatedAt,
  toggleText: estimateToggleText,
  realtime: estimateQuotes
} = usePositionValuation(rawHoldings);

/** 每个标签分组每页显示 20 条（组内分页由 StrategyGroupSection 自己管页码） */
const groupPageSize = 20;

const {
  allTags,
  positionTagMap,
  setOverview,
  unbindTag,
  updateTags,
  createTagForRow,
  createGlobalTag,
  deleteGlobalTag
} = useStrategyTags();

async function fetchAll() {
  loading.value = true;
  try {
    const res = await getStrategyOverview();
    const { holdings = [], tags = [], relations = {} } = res.data ?? {};

    rawHoldings.value = enrichHoldings(holdings, relations, confirmedPnl);
    setOverview(tags, relations);
  } catch (e) {
    ElMessage.error("加载策略视图失败");
  } finally {
    loading.value = false;
  }
}

// 汇总数据（取原始持仓，避免多标签重复计算）
const totalHoldings = computed(() => rawHoldings.value.length);
const totalMarketValue = computed(() => sumMarketValue(rawHoldings.value));
const totalPnl = computed(() => sumPnl(rawHoldings.value));

/**
 * 标签走**当前映射**而不是取数时的快照：勾选/取消后映射变了、持仓对象没变。
 * 少了这一步，标签改动只落在请求上，表格徽标与分组都不会跟着动。
 */
const enrichedHoldings = computed(() =>
  applyTags(rawHoldings.value, positionTagMap.value)
);

// 按标签分组
const strategyGroups = computed(() =>
  buildStrategyGroups(enrichedHoldings.value)
);

onMounted(() => {
  fetchAll();
});
</script>

<style scoped>
.strategies-page {
  /* 继承全局字体 token，避免与站内其它页面字体不一致（design-tokens.css --font-ui） */
  font-family: var(--font-ui);

  /* 数字等宽对齐：消除金额/计数宽度抖动（design.md「数字等宽对齐」） */
  font-variant-numeric: tabular-nums;
}

/* 标题口径 ⓘ：与 SectionHeader 的信息图标同款交互（hover / 键盘聚焦） */
.strategy-scope__info {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-body);
  color: var(--text-tertiary-ink);
  cursor: help;
}

.strategy-scope__info:hover,
.strategy-scope__info:focus-visible {
  color: var(--brand-700);
  outline: none;
}

/* 产品单元格 */
.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
}

.product-name {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.product-code-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.product-code {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.type-tag-inline {
  height: 20px;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 20px;
  color: var(--text-inverse);
  background-color: var(--bg-page);
  border: none;
}
</style>
