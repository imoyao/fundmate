<!--
  交易流水表的操作列单元格（2026-11-12 从 index.vue 拆出：那个文件顶着
  `check_vue_size.mjs` 的 400 行门禁，行级编辑判据加不进去，而操作列本来就是
  自洽的一块——样式、置灰语义、两个按钮都不该再往骨架里塞）。
-->
<script setup lang="ts">
import type { TransactionRow } from "./model";

const props = defineProps<{
  row: TransactionRow;
  /** 编辑 / 删除按钮的显隐由容器声明（哪些表开放哪种操作是容器口径） */
  showEdit?: boolean;
  showDelete?: boolean;
  /**
   * 行级编辑判据（可选，默认不判——所有行可编辑，既有调用零变化）。
   * 返回非空字符串 = 该行编辑按钮置灰，字符串同时就是 tooltip 文案；
   * 后端限制（如 PATCH 只接受已归属账本的流水）由容器翻译成这句话。
   */
  editDisabledReason?: (row: TransactionRow) => string;
}>();

const emit = defineEmits<{
  edit: [row: TransactionRow];
  delete: [row: TransactionRow];
}>();

/** 空串 = 可编辑；非空 = 置灰原因（tooltip 与 disabled 共用这一个判断） */
function editBlocked(row: TransactionRow): string {
  return props.editDisabledReason?.(row) ?? "";
}
</script>

<template>
  <!-- 编辑：置灰时由外层 span 接 hover（原生 disabled 按钮不派发鼠标事件），
       tooltip 说明「为什么不能点」——禁止只置灰不解释（design.md 行内操作交互规范）。 -->
  <div class="txn-table__actions">
    <el-tooltip
      v-if="showEdit"
      :disabled="!editBlocked(row)"
      :content="editBlocked(row)"
      placement="top"
    >
      <span class="txn-table__action-slot">
        <el-button
          text
          size="small"
          :disabled="!!editBlocked(row)"
          @click.stop="emit('edit', row)"
          >编辑</el-button
        >
      </span>
    </el-tooltip>
    <el-button
      v-if="showDelete"
      text
      size="small"
      type="danger"
      @click.stop="emit('delete', row)"
      >删除</el-button
    >
  </div>
</template>

<style scoped>
/* 行内操作 hover 淡入（design.md「行内操作交互规范」：默认 opacity 0，
   hover 行 200ms ease-out 淡入）。
   ⚠️「行 hover → 淡入」那条**必须留在父组件** `TransactionTable/index.vue`：
   `.el-table__row`（tr）是本单元格的**祖先**，而 scoped 的 `:deep(X) Y`
   会编译成 `[data-v-cell] X Y`，只在**后代**里找 X ⇒ 写在这里永远不匹配，
   按钮对鼠标用户恒为 opacity 0（2026-11-12 实测编译产物）。
   两个可达性兜底中，作用于自身根元素的这两条留在此处（guard_a11y_interaction）：
   - :focus-within：键盘 Tab 到按钮即显现；
   - @media (hover: none)：触屏设备没有 hover 态，按钮常驻——
     否则触屏用户永远点不到「编辑」。 */
.txn-table__actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  white-space: nowrap;
  opacity: 0;
  transition: opacity 200ms ease-out;
}

.txn-table__actions:focus-within {
  opacity: 1;
}

@media (hover: none) {
  .txn-table__actions {
    opacity: 1;
  }
}

/* 置灰按钮的 tooltip 触发层：与按钮同尺寸的透明 span，不改按钮自身的 disabled 基线 */
.txn-table__action-slot {
  display: inline-flex;
}
</style>
