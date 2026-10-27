<script setup lang="ts">
/**
 * 渐进披露的第二 / 第三级控制（#980 拆分）。
 *
 * - 第二级：「展开全部 N 条」**就地展开**，表内滚动（高度上限交给 el-table 的
 *   max-height，由它原生固定表头，比手写 sticky 稳）。
 * - 第三级：展开后仍看不全时给「查看全部流水」出口。**只在展开态出现**——
 *   折叠态就摆这条链接，是在给一个多数用不到的出口加噪声。
 *
 * 父级只在 `needToggle` 为真时挂载本组件；`showsPartial` 成立时 `needToggle`
 * 必然成立（展开态意味着总量已超过折叠态），所以这里不必再判一次。
 */
defineProps<{
  total: number;
  expanded: boolean;
  /** 展开态的增量加载中：此时已有 10 行在屏上，不能再换骨架屏 */
  expanding: boolean;
  /** 已取到但少于总量（展开态才可能为真） */
  showsPartial: boolean;
  /** 已取到的条数（部分提示里的「最近 N 条」） */
  taken: number;
}>();

defineEmits<{
  (e: "toggle"): void;
  (e: "go-all"): void;
}>();
</script>

<template>
  <button
    type="button"
    class="transaction-section__more"
    :aria-expanded="expanded"
    aria-controls="transaction-detail-table"
    :disabled="expanding"
    @click="$emit('toggle')"
  >
    {{ expanding ? "加载中…" : expanded ? "收起" : `展开全部 ${total} 条` }}
  </button>

  <p v-if="showsPartial" class="transaction-section__footnote">
    仅显示最近 {{ taken }} 条 ·
    <button
      type="button"
      class="transaction-section__link"
      @click="$emit('go-all')"
    >
      查看全部流水
    </button>
  </p>
</template>

<style lang="scss" scoped>
@use "./transaction-base";

/* 展开/收起是主操作，给品牌色；「查看全部流水」是次级出口，弱化成普通链接 */
.transaction-section__more {
  align-self: flex-start;
  padding: 0;
  font-size: var(--text-label);
  color: var(--brand-700, var(--brand-500));
  cursor: pointer;
  background: none;
  border: none;
}

.transaction-section__more:hover:not(:disabled) {
  text-decoration: underline;
}

.transaction-section__more:disabled {
  color: var(--text-tertiary);
  cursor: default;
}

.transaction-section__more:focus-visible,
.transaction-section__link:focus-visible {
  outline: 2px solid var(--brand-500);
  outline-offset: 2px;
  border-radius: var(--radius-sm, 4px);
}

.transaction-section__link {
  padding: 0;
  font-size: var(--text-label);
  color: var(--brand-700, var(--brand-500));
  cursor: pointer;
  background: none;
  border: none;
}

.transaction-section__link:hover {
  text-decoration: underline;
}
</style>
