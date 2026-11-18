<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { InputInstance } from "element-plus";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import type { EditField, PreviewRow } from "../composables/previewRow";

const props = defineProps<{ row: PreviewRow; field: EditField }>();

const { startEdit, finishEdit, cancelEdit } = useImportWizardContext();

const FIELD_LABEL: Record<EditField, string> = {
  quantity: "数量",
  price: "单价",
  amount: "金额",
  fee: "手续费"
};

/** 编辑态由 useImportWizard 驱动（单行单格互斥），此处只读展示 */
const editing = computed(() => {
  const r = props.row;
  if (props.field === "quantity") return !!r.isEditingQty;
  if (props.field === "price") return !!r.isEditingPrice;
  if (props.field === "fee") return !!r.isEditingFee;
  return !!r.isEditingAmount;
});

/**
 * 四个可编辑字段在行上的「线上值」：正常是数字；被清空后写进去的是**空串哨兵**
 * （见 `onInput`——`isRowBlocked` 据空串判缺项，行转「待补全」）。
 *
 * 空串不在 `ImportPreviewRow` 的类型里，而这是全仓**唯一**有意越界写这四个字段的
 * 地方。收敛方式不是把行字段放宽成 `number | ""`（那会让所有读侧都以为可能拿到
 * 空串、等于把 any 换个写法），而是把越界圈在下两行里：写走 `setEditableValue`，
 * 读走 `editableValue`，其余代码照旧按 number 理解行值。
 */
type EditableValue = number | "";

function editableValue(): EditableValue {
  return (props.row as unknown as Record<EditField, EditableValue>)[
    props.field
  ];
}

function setEditableValue(value: EditableValue): void {
  (props.row as unknown as Record<EditField, EditableValue>)[props.field] =
    value;
}

const isEmpty = computed(() => {
  const v = editableValue();
  return v === null || v === undefined || v === "";
});

/**
 * 手续费展示：0 / 空一律显示占位「—」而不是「0」「待补全」。
 * WHY：大多数行没有费用，满屏 0 会让「哪一行真的有费用」看不出来；而 fee 缺失
 * 不构成阻断（isRowBlocked 不看 fee），「待补全」的红色语义会被误读成必须填。
 * 展示为占位、点击仍可就地补录，两个需求都保住。
 */
const feeText = computed(() => {
  const n = Number(props.row.fee);
  return !n ? "—" : n.toFixed(2);
});

const displayRef = ref<HTMLElement | null>(null);
const inputRef = ref<InputInstance | null>(null);
/**
 * 输入草稿：行值随输入实时写回 row[field]（saveAllEditingRows / 点击切格兜底
 * 能拿到新值），Esc 统一由 finishEdit 从 _oldValue 还原——与既有弹层编辑的
 * 取消语义一致。
 */
const draft = ref("");

/** 只接受纯数字中间态：`-` / `abc` 这类半截输入留在草稿里，不污染行值与分类判定 */
const NUM_RE = /^-?\d*\.?\d*$/;

function focusInput() {
  const inst = inputRef.value;
  // el-input 暴露了原生 input 元素；$el 兜底只在实例尚未完成挂载时走到
  const el =
    inst?.input ??
    (inst?.$el as HTMLElement | undefined)?.querySelector<HTMLInputElement>(
      "input"
    );
  el?.focus();
}

/** 就地进入编辑：状态由 useImportWizard 置位，草稿与聚焦统一交给下方 watch */
function enterEdit() {
  startEdit(props.row, props.field);
}

/**
 * 编辑态开启 → 同步草稿并自动聚焦。
 * 放 watch 而非点击路径里：外部触发（操作列【补全】直接调 startEdit）不经过
 * 本组件的 enterEdit，必须同样拿到正确草稿与聚焦（#1790 补全入口）。
 */
watch(editing, on => {
  if (!on) return;
  const v = editableValue();
  draft.value = v === null || v === undefined ? "" : String(v);
  nextTick(() => focusInput());
});

function onInput(val: string) {
  draft.value = val;
  if (val === "") {
    // 清空 → isRowBlocked 视作缺项，行转待补全（空串哨兵，见 editableValue 注释）
    setEditableValue("");
    return;
  }
  if (!NUM_RE.test(val)) return;
  const n = parseFloat(val);
  if (!isNaN(n)) {
    setEditableValue(n);
  }
}

function stayOnCell() {
  nextTick(() => displayRef.value?.focus());
}

function onKeydown(e: KeyboardEvent) {
  if (!editing.value) return;
  if (e.key === "Enter") {
    e.preventDefault();
    finishEdit(props.row, props.field, true); // 提交（smartFill + 金额重算）
    stayOnCell(); // 并停留当前格：Enter 可再次进入
  } else if (e.key === "Escape") {
    e.preventDefault();
    cancelEdit(props.row, props.field); // 取消还原
    stayOnCell();
  } else if (e.key === "Tab") {
    e.preventDefault();
    tabToNext();
  }
}

/**
 * Tab：提交并跳下一可编辑格。DOM 顺序即列序（行内 数量→单价→金额→下一行…），
 * 天然跨行；末格没有下一格时提交并停留当前格。
 */
function tabToNext() {
  finishEdit(props.row, props.field, true);
  nextTick(() => {
    const cells = Array.from(
      document.querySelectorAll<HTMLElement>("[data-edit-cell]")
    );
    const idx = cells.findIndex(
      el =>
        el.dataset.editCell === props.field &&
        el.dataset.rowKey === String(props.row._rowKey)
    );
    const next = idx >= 0 ? cells[idx + 1] : undefined;
    if (next) {
      next.focus();
      next.click(); // 落点即进入编辑（与点击同一路径）
    } else displayRef.value?.focus();
  });
}
</script>

<template>
  <div class="edit-cell" @keydown="onKeydown">
    <!-- 就地编辑态：非浮层（#1790；规范 #783 §6.2「就地转为输入框，不使用弹出层」） -->
    <el-input
      v-if="editing"
      ref="inputRef"
      v-model="draft"
      size="small"
      inputmode="decimal"
      :aria-label="`${FIELD_LABEL[field]}编辑中，Enter 提交、Esc 取消、Tab 下一格`"
      @input="onInput"
    />
    <!-- 展示态：单击 / Enter 进入编辑 -->
    <span
      v-else
      ref="displayRef"
      class="edit-cell__display"
      role="button"
      tabindex="0"
      :data-edit-cell="field"
      :data-row-key="row._rowKey"
      :aria-label="`编辑${FIELD_LABEL[field]}`"
      @keydown.enter.stop.prevent="enterEdit"
      @keydown.space.stop.prevent="enterEdit"
      @click.stop="enterEdit"
      @mousedown.prevent
    >
      <template v-if="field === 'fee'">
        <span :class="{ 'fee-zero': feeText === '—' }">{{ feeText }}</span>
      </template>
      <template v-else-if="!isEmpty">
        {{ row[field] }}
        <el-tag
          v-if="row.is_calculated"
          size="small"
          type="warning"
          class="ml-1"
          >待确认</el-tag
        >
      </template>
      <span v-else class="cell-pending">待补全</span>
    </span>
  </div>
</template>

<style scoped>
.edit-cell {
  width: 100%;
}

.edit-cell__display {
  display: inline-block;
  max-width: 100%;
  cursor: pointer;
  user-select: none;
}

.edit-cell__display:hover {
  color: var(--el-color-primary);
}

/* 无费用占位：低于正文一级，避免满屏 0 抢注意力 */
.fee-zero {
  color: var(--text-tertiary-ink);
}
</style>
