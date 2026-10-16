<!--
  PnlDualLine · 盈亏双线（设计系统组件，#1104）

  两行同显，口径必须可辨：
  - 主行「已确认」：T-1 确认净值 / 最近交易日收盘价口径（后端权威值，可复算）；
  - 副行「预估」：盘中实时行情估算口径，带「估」标记 + 免责 tooltip，用户可感知。

  为什么不做成「切换」而是「同显」：切换只能看到一个数，用户无从判断
  「我现在看到的是确认值还是估值」；同显时两条线的差异本身就是信息
  （盘中估值相对确认净值的偏移）。切换器由调用方按需另行提供。

  纯展示组件：不取数、不推断口径，两个值由调用方（`usePositionValuation`）传入。
  副行抽成 `PnlEstimateLine`（#1104）：自选页的主行是 `MoneyWithRatio`，
  套不进本组件，但副行口径必须与这里一致，故不能各写一份。

  价格时点（#2140）：调用方传行级 `priceDate` 时，「已确认」tag 悬停说明
  「截至哪天」——时点是行级精确值（基金=实际采用的最新净值日），不做区块级
  聚合日期（分页 + 混源下聚合会失真）。缺省 null 时无 tooltip，维持旧行为。
-->
<template>
  <div class="pnl-dual-line" :class="`pnl-dual-line--${size}`">
    <!-- 主行：已确认（权威口径）。带价格时点时（#2140）tooltip 说清「截至哪天」 -->
    <div class="pnl-dual-line__row">
      <el-tooltip v-if="priceDateTip" :content="priceDateTip" placement="top">
        <span class="pnl-dual-line__tag pnl-dual-line__tag--dated">已确认</span>
      </el-tooltip>
      <span v-else class="pnl-dual-line__tag">已确认</span>
      <MoneyDisplay
        :value="confirmed"
        :show-sign="true"
        :size="size"
        empty-text="--"
      />
    </div>

    <!-- 副行：当日预估（估值口径）。拿到真实行情才显示数字 -->
    <PnlEstimateLine
      :estimated="estimated"
      :hint="hint"
      :source="source"
      :source-time="sourceTime"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PnlEstimateLine from "@/components/PnlEstimateLine/index.vue";

const props = withDefaults(
  defineProps<{
    /** 已确认盈亏（T-1 口径）；null / undefined 渲染为 `--` */
    confirmed?: number | null;
    /** 当日预估盈亏（估值口径）；null 表示拿不到真实行情，此时不显示数字 */
    estimated?: number | null;
    /** 预估不可用时的副行提示（由调用方按原因给出，见 usePositionValuation.estimateHint） */
    hint?: string;
    /** 估值来源标识（#2143 契约透传；缺省徽标不缀名） */
    source?: string | null;
    /** 行情数据时间字符串（源端原样，#2143 契约透传） */
    sourceTime?: string | null;
    /**
     * 已确认口径的价格时点（#2140）：后端行级 price_date（基金=实际采用的最新
     * 净值日，其他=快照回写日）。非空时「已确认」tag 挂 tooltip 说明截至日期；
     * null 则无 tooltip（维持旧行为，不为没有时点的数据编日期）。
     */
    priceDate?: string | null;
    /** 主行金额字号；副行恒为 xs（维持主次层级） */
    size?: "sm" | "md";
  }>(),
  {
    confirmed: null,
    estimated: null,
    hint: "",
    source: null,
    sourceTime: null,
    priceDate: null,
    size: "sm"
  }
);

/** 「已确认」tag 的时点说明；无时点返回空串（不挂 tooltip） */
const priceDateTip = computed(() =>
  props.priceDate
    ? `已确认口径：官方净值 / 收盘价，价格截至 ${props.priceDate}`
    : ""
);
</script>

<style scoped>
/* 右对齐堆叠：金额始终贴右缘，两行数字天然对齐，便于纵向扫读 */
.pnl-dual-line {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-end;
  line-height: 1.3;
}

.pnl-dual-line__row {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

/* 口径标签：次级文字色，字号随档位（11/12px），不参与涨跌着色 */
.pnl-dual-line__tag {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 带价格时点的 tag（#2140）：挂了 tooltip，给出「可悬停」的 affordance */
.pnl-dual-line__tag--dated {
  cursor: help;
}

.pnl-dual-line--md .pnl-dual-line__tag {
  font-size: 12px;
}
</style>
