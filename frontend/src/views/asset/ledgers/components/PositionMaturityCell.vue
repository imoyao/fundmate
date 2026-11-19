<!--
  PositionMaturityCell · 持仓表「产品信息」格里的到期日短标签（#931 / D121）

  为什么是一枚可点的文本而不是新增一列：账户详情持仓表 10 列已吃满 1080/1082 的宽度
  预算（见 `LedgerDetailHoldingsPane` 「所属组合」列上的注释），再加列会把「配置目标」
  推进 fixed 操作列底下。而「什么时候到期」正是看产品名时会顺带问的问题，放在产品名
  下面一行最省发现成本。

  只做「显示 + 触发编辑」：弹窗留在父页，避免 `el-dialog` 嵌进表格单元格后被行重渲染
  连坐（弹窗状态不该挂在一行数据上）。
-->
<template>
  <button
    v-if="isMaturityEditable(row.asset_type)"
    type="button"
    class="maturity-chip"
    :class="{ 'is-due': maturityState(row.maturity_date) === 'due' }"
    @click.stop="emit('edit', row)"
  >
    {{ maturityChipText(row.maturity_date) }}
  </button>
</template>

<script setup lang="ts">
import type { LedgerHoldingRow } from "@/composables/ledger/types";
import {
  isMaturityEditable,
  maturityChipText,
  maturityState
} from "./positionMaturity";

defineOptions({ name: "PositionMaturityCell" });

defineProps<{ row: LedgerHoldingRow }>();

/** 父页拿去打开弹窗：本组件不持有弹窗状态（见文件头） */
const emit = defineEmits<{ (e: "edit", row: LedgerHoldingRow): void }>();
</script>

<style lang="scss" scoped>
/* 长得像文本，不像按钮——表格里密集数字中间冒出一个实心按钮会抢走「市值 / 盈亏」的
   视线。hover 才显形为「可点」（下划线 + 主文本色）。
   is-due 用 `--color-warning-ink`（告警**文字**级）：到期当日逆回购已转现金，这一行
   与「它还是一笔投资」的直觉不一致，值得到一眼。列上已有 show-overflow-tooltip，
   故这里按单行截断。 */
.maturity-chip {
  display: block;
  max-width: 100%;
  padding: 0;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  line-height: 1.4;
  color: var(--text-tertiary-ink);
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  background: none;
  border: 0;

  &:hover {
    color: var(--brand-ink);
    text-decoration: underline;
  }

  &.is-due {
    color: var(--color-warning-ink);
  }
}
</style>
