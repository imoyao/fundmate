<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import { visibleSourceOp } from "../composables/sourceOpText";

const props = defineProps<{ row: any }>();

const { getFundTypeColor } = useImportWizardContext();

/**
 * 类型标签是否在本列显示。
 *
 * 「操作类型」列（OpTypeCell）已经显示过资产类型标签（买入 · 股票），本列再显示一次
 * 是把同一条信息说两遍——代价还是从最紧的备注里扣的：实测 1440 视口下备被压成「备…」。
 * 故只在「这一列才有」的情况下显示：
 * - 基金：OpTypeCell 对 fund 不显示类型标签，而基金的类型（股票型/债券型…）只在这里；
 * - 合并行：OpTypeCell 对 is_merged 行也不显示。
 */
const showTypeTag = computed(() => {
  const r = props.row;
  if (!r.display_type) return false;
  return r.type === "fund" || Boolean(r.is_merged);
});

/**
 * 券商原文（`notes`）只在它带来新信息时才显示（判据见 composables/sourceOpText.ts）。
 * 「证券买入」这类与操作列重复的写法直接不渲染——它挤掉的是产品列里更该被看见的东西。
 */
const srcOp = computed(() => visibleSourceOp(props.row));
</script>

<template>
  <div class="product-cell">
    <!-- #2836：券商原文从「代码行」挪到「名称行」。
         代码行被 `#` + 6 位代码吃掉约 66px，留给备注只剩 70px——正好卡在
         「债券兑息兑付」6 个字（72px）的边上，于是每个真实备注都被截成
         「债券兑息兑…」这种半个词，信息价值归零。名称通常是 4 个字，让出
         的空间刚好够备注完整显示，且**不增加行高**（仍是两行结构）。
         hover 仍给全文与「会写进备注」的说明。 -->
    <div class="product-name-row">
      <span class="product-name">{{ row.name || row.symbol || "--" }}</span>
      <span
        v-if="srcOp"
        class="product-notes"
        :title="`券商原文：${row.notes}（会写进该笔流水的备注）`"
        >{{ srcOp }}</span
      >
    </div>
    <div class="product-code-row">
      <span class="product-code"># {{ row.symbol || "--" }}</span>
      <el-tag
        v-if="showTypeTag"
        size="small"
        :color="getFundTypeColor(row.display_type)"
        class="type-tag-inline"
        >{{ row.display_type }}
      </el-tag>
    </div>
  </div>
</template>

<style scoped>
.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
}

.product-name-row {
  display: flex;
  gap: 6px;
  align-items: baseline;
  min-width: 0;
}

.product-name {
  flex: 0 0 auto;
  max-width: 62%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.product-code-row {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.product-code {
  flex: 0 0 auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 备注：唯一可压缩项，超出截断（title 给全文）。
   刻意与名称同行而不与代码同行——见模板注释。 */
.product-notes {
  flex: 1 1 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.type-tag-inline {
  flex: 0 0 auto;
  height: 20px;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 20px;
  color: var(--text-inverse);
  border: none;
}
</style>
