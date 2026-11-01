<script setup lang="ts">
/**
 * 交易流水 · 资产单元格（名称 + 代码位 + 状态标记）。
 *
 * 从 `TransactionTable/index.vue` 拆出：它同时是这个页面里**唯一**该说明
 * 「这条流水对应的持仓怎么了」的地方，而三种态（持有 / 已清仓 / 资金流水）撞在
 * 一个 `v-if` 链里，会和「有没有代码」「要不要打灰」混成一团——那正是 #980 打出
 * 「已删除」、把真实流水涂成失效数据的起点。
 *
 * ## 三条互斥的渲染
 *
 * | 态 | 名称旁 | 代码位 | 行底色 |
 * |---|---|---|---|
 * | `held` | 无 | 有则显示 | 正常 |
 * | `cleared` | 已清仓胶囊（`title` 说明为什么保留） | 有则显示 | **正常，不打灰** |
 * | `account` | 「资金流水」弱化字 | 不显示 | 正常 |
 *
 * **`cleared` 不打灰**是这次设计的硬约束：用户做的是清仓，不是删除。整格
 * `opacity .5 + grayscale` 会把一条真实发生过的买入说得像失效数据，金额与日期一起
 * 看不清，顺带毁掉可读性。
 */
import { computed } from "vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import {
  assetCodeText,
  CLEARED_BADGE_TITLE,
  isAccountLevel,
  positionStateOf,
  type TransactionRow
} from "./model";

const props = defineProps<{ row: TransactionRow }>();

const state = computed(() => positionStateOf(props.row));
const code = computed(() => assetCodeText(props.row));
const accountLevel = computed(() => isAccountLevel(props.row));
</script>

<template>
  <div class="txn-asset">
    <!-- 代码位为空时整段不渲染（show-code=false）：内部占位码与资金流水都没有代码，
         印一个 `# --` 只是把空缺画出来。无障碍名由资产名承担。 -->
    <ProductDisplay
      :name="row.position_name"
      :symbol="code ?? undefined"
      :show-code="!!code"
    />
    <span v-if="accountLevel" class="txn-asset__kind">资金流水</span>
    <span
      v-else-if="state === 'cleared'"
      class="txn-asset__badge"
      :title="CLEARED_BADGE_TITLE"
      >已清仓</span
    >
  </div>
</template>

<style scoped>
.txn-asset {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 6px;
  align-items: center;
}

/* 已清仓：安静的胶囊（软底 + 次要字色），不是警告色。
   用文字而不是灰度表达状态——灰度会让整行金额一起变淡。 */
.txn-asset__badge {
  padding: 1px 6px;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  background: var(--bg-soft);
  border-radius: var(--radius-small, 4px);
}

/* 资金流水：比标签更弱——它只是「这一行没有标的」，不是状态 */
.txn-asset__kind {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}
</style>
