<!--
  PnlEstimateLine · 「预估」副行（#1104 抽出复用）

  为什么单独抽成一个组件：这条副行有**两个**消费方，口径与免责提示必须一致——

  1. `PnlDualLine`（全面盘点 / 账户详情 / 组合详情 / 策略分析的盈亏列）：
     主行「已确认」+ 本副行；
  2. 自选页「持仓收益」列：主行是 `MoneyWithRatio`（金额 + 百分比二合一，套不进
     `PnlDualLine`），但副行同样要「估」徽章 + 免责 tooltip。

  抽出来之前这两处只能各写一份，违反 `components.md`「禁止各页重写同类结构」。

  「估」徽章（#2143 起为 `ValuationSourceBadge` 统一实现）是唯一视觉锚点：
  完整免责 tooltip（文案 `ESTIMATE_DISCLAIMER`，单一出口）紧贴数字，
  来源 / 数据时间作为元信息缀入 tooltip 与读屏文案（有则显示）。

  视觉层级（#2210）：副行一旦带数字，就是「第二组金额」，必须比主行弱——
  整行（徽章 + 金额）退到 0.72 强度（`is-weak`）。纯提示文字态（未开启 / 不参与，
  无数字）不叠加弱化：本就三级色 11px，再降会跌破可读对比度。
-->
<template>
  <!-- 既无预估、也无提示文案 → 整行不渲染。
       自选页这种高密度表格不需要逐行复述「未开启实时估值」；
       需要复述的表格（全面盘点 / 账户详情…）由调用方传 `hint`。 -->
  <span
    v-if="hasEstimated || hint"
    class="pnl-estimate-line"
    :class="{ 'is-weak': hasEstimated }"
  >
    <el-tooltip v-if="hasEstimated" :content="tipText" placement="top">
      <ValuationSourceBadge
        status="estimated"
        :source="source"
        :source-time="sourceTime"
        :tip="ESTIMATE_DISCLAIMER"
      />
    </el-tooltip>
    <span v-else class="pnl-estimate-line__tag">预估</span>

    <MoneyDisplay
      v-if="hasEstimated"
      :value="estimated"
      :show-sign="true"
      size="xs"
    />
    <span v-else class="pnl-estimate-line__hint">{{ hint }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import { valuationMetaText } from "@/components/ValuationSourceBadge/helpers";
import { ESTIMATE_DISCLAIMER } from "@/composables/usePositionValuation";

const props = withDefaults(
  defineProps<{
    /** 预估金额；`null` 表示拿不到真实行情（此时不显示数字） */
    estimated?: number | null;
    /** 拿不到预估时的提示文案；留空则整行不渲染（密集表格用） */
    hint?: string;
    /** 估值来源标识（Quote.provider / 后端 source）；缺省不缀名 */
    source?: string | null;
    /** 行情数据时间（源端字符串原样）；缺省不缀时 */
    sourceTime?: string | null;
  }>(),
  { estimated: null, hint: "", source: null, sourceTime: null }
);

const hasEstimated = computed(
  () => props.estimated != null && !Number.isNaN(props.estimated)
);

/** tooltip 内容 = 免责主句（ESTIMATE_DISCLAIMER 单一出口）+ 元信息（有则缀） */
const tipText = computed(() => {
  const meta = valuationMetaText(props.source, props.sourceTime);
  return meta ? `${ESTIMATE_DISCLAIMER}（${meta}）` : ESTIMATE_DISCLAIMER;
});
</script>

<style scoped>
/* inline-flex：在「右对齐的容器」里跟随文本对齐贴右缘（自选页单元格），
   在 `PnlDualLine` 的列向 flex 里则由父级 align-items: flex-end 贴右缘。 */
.pnl-estimate-line {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  line-height: 1.3;
}

/* 带数字的副行（#2210 视觉层级）：整行退到 0.72 强度——与 MoneyWithRatio
   比例行同一弱化档（主行金额 100% > 主行比例 72% ≈ 副行 72%，层级由
   「组距 + 徽章 + 币值」区分）。opacity 只降强度不改色：涨红跌绿语义保留，
   不新增任何色值，暗色由令牌自动成立。 */
.pnl-estimate-line.is-weak {
  opacity: 0.72;
}

/* 口径标签：次级文字色，固定 11px（副行恒比主行弱一档，不随 PnlDualLine 的 size 变） */
.pnl-estimate-line__tag {
  flex-shrink: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 「估」徽章的视觉住在 `ValuationSourceBadge`（#2143 统一实现），本组件只负责外套 tooltip */

/* 预估不可用时的提示：比口径标签更弱，避免在表格里抢注意力 */
.pnl-estimate-line__hint {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}
</style>
