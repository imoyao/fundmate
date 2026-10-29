<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getPositionAdvisorContext,
  type PositionAdvisorContext
} from "@/api/positions";
import { advisorOpTone, advisorRatioText } from "@/utils/advisorAdjust";

/**
 * 持仓页「主理人最近调仓」（#2740 / D70）。
 *
 * ## 这块回答什么、不回答什么
 *
 * 回答：**我持有的这个投顾组合，主理人最近动过什么**。
 * 不回答：我自己账户里买卖了什么——那是「交易记录」区块。
 *
 * 两者的区别必须写在脸上：调仓是主理人对**组合**的调整，我的持仓金额与成本**不会**
 * 因此变化（本系统只提示、不自动跟调，#2740 边界明文）。旧版没有这块时，用户只能
 * 看到一坨金额，看不出这个组合是「活的」。
 *
 * ## 三态降级（都不显示成错误）
 *
 * - 拉取失败（网络 / 500）：说「暂时取不到」，不冒充「没有调仓」；
 * - `data === null`（后端契约）：本地从没同步过该组合的 market 域数据。这是**数据完整性**
 *   问题，不是这笔记账坏了——持仓金额、成本、盈亏照常，所以只提示一句；
 * - `adjusts` 为空数组：确实没有调仓记录；且慢的来源是持仓快照序列推导，
 *   空态要额外说明「不是故障」（与速览抽屉同一口径）。
 *
 * 口径复用：比例文案与方向判定走 `@/utils/advisorAdjust`，与自选速览抽屉同源，
 * 避免同一条调仓记录在两个页面显示成两种样子。
 */
const props = defineProps<{
  /** 投顾组合持仓 id（同一组合跨账户取任一行即可，调仓明细与账户无关） */
  positionId: number;
}>();

const loading = ref(false);
const failed = ref(false);
const data = ref<PositionAdvisorContext | null>(null);

/** 且慢的调仓由持仓快照推导，空态需要解释「不是故障」 */
const emptyHint = computed(() =>
  data.value?.platform === "QIEMAN"
    ? "暂无调仓记录（且慢按持仓快照推导，需累积 ≥2 次快照）"
    : "暂无调仓记录"
);

async function load() {
  if (!props.positionId) return;
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    const res = await getPositionAdvisorContext(props.positionId);
    data.value = res.data ?? null;
  } catch {
    // 提示位拉不到不影响持仓本身，不显示错误态、不阻塞其余区块
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.positionId, load, { immediate: true });
</script>

<template>
  <CardBlock class="advisor-adjusts">
    <SectionHeader
      title="主理人最近调仓"
      info="组合主理人对该组合成分基金的调整记录，仅作提示：它不是你自己账户里的买卖，也不会自动跟调。你的持仓金额与成本不因此变化。"
      info-label="关于主理人调仓"
    >
      <template #badge>
        <span class="advisor-adjusts__badge">仅提示</span>
      </template>
    </SectionHeader>

    <p class="advisor-adjusts__note">
      这是组合主理人的调仓，不是你自己的操作；本系统不会自动跟调。
    </p>

    <p v-if="loading" class="advisor-adjusts__hint">正在读取主理人调仓…</p>
    <p v-else-if="failed" class="advisor-adjusts__hint">
      主理人调仓暂时取不到，稍后再看。
    </p>
    <p v-else-if="!data" class="advisor-adjusts__hint">
      本地暂未收录该组合的调仓数据，不影响你的持仓金额与成本。
    </p>
    <p v-else-if="!data.adjusts.length" class="advisor-adjusts__hint">
      {{ emptyHint }}
    </p>
    <div v-else class="advisor-adjusts__list">
      <div
        v-for="group in data.adjusts"
        :key="group.adjust_date"
        class="advisor-adjusts__group"
      >
        <div class="advisor-adjusts__head">
          <span class="advisor-adjusts__date">{{ group.adjust_date }}</span>
          <span class="advisor-adjusts__count">
            {{ group.items.length }} 只调整
          </span>
        </div>
        <p v-if="group.reason" class="advisor-adjusts__reason">
          {{ group.reason }}
        </p>
        <ul class="advisor-adjusts__items">
          <li
            v-for="item in group.items"
            :key="`${group.adjust_date}-${item.fund_code}`"
            class="advisor-adjusts__item"
          >
            <span
              class="advisor-adjusts__name"
              :title="item.fund_name || item.fund_code"
            >
              {{ item.fund_name || item.fund_code }}
            </span>
            <span class="advisor-adjusts__ratio">
              <span
                class="advisor-adjusts__op"
                :class="`advisor-adjusts__op--${advisorOpTone(item.op_name)}`"
              >
                {{ item.op_name || "调整" }}
              </span>
              {{ advisorRatioText(item) }}
            </span>
          </li>
        </ul>
      </div>
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
.advisor-adjusts {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

/* 「仅提示」胶囊：中性色（不是警告色也不是涨跌色），呼应 Badge 规范 */
.advisor-adjusts__badge {
  flex-shrink: 0;
  padding: 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-muted, var(--bg-page));
  border-radius: var(--radius-pill);
}

/* 定调句：把「不是我自己的调仓」说在最前面，避免误读成本区块的记账变动 */
.advisor-adjusts__note {
  margin: 0 0 var(--space-3);
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.advisor-adjusts__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.advisor-adjusts__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.advisor-adjusts__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin-bottom: var(--space-1);
}

.advisor-adjusts__date {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.advisor-adjusts__count {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 主理人的调仓说明（原文，不做截断——理由短，截断反而看不懂） */
.advisor-adjusts__reason {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.advisor-adjusts__items {
  padding: 0;
  margin: 0;
  list-style: none;
}

.advisor-adjusts__item {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  padding: 2px 0;
  font-size: var(--text-label);
}

.advisor-adjusts__name {
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
}

.advisor-adjusts__ratio {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.advisor-adjusts__op {
  margin-right: var(--space-1);
}

/* 加仓/减仓用涨跌语义变量（不硬编码色值），其余操作保持中性 */
.advisor-adjusts__op--add {
  color: var(--color-rise-ink);
}

.advisor-adjusts__op--cut {
  color: var(--color-fall-ink);
}
</style>
