<script setup lang="ts">
import { computed, ref } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import type { PreviewRow } from "../composables/previewRow";
import { visibleSourceOp } from "../composables/sourceOpText";

const props = defineProps<{ row: PreviewRow }>();

const { getFundTypeColor } = useImportWizardContext();

/**
 * 打新中签建仓的代码补全（后端 ipo_events.py 写入的 link_warning 前缀，前后端契约）。
 *
 * 券商交割单只给申购代码，上市代码无法从文件内可靠推导，故折叠器保留申购码并
 * 标 link_warning。这里让**仅这一档**行的代码可就地编辑：改完直接写回 row.symbol，
 * 而 commit_from_preview 正是取 row['symbol'] 落库（orchestrator_commit.py:136）。
 * 不改数字字段的 EditableCell（它只接受数值），也不对整表开放代码编辑，避免误改。
 */
const SYMBOL_ALIAS_HINT = "打新中签建仓";
// 与后端 CMS_IPO_LISTED_CODE_PREFIXES 一致：补全成可转债代码时同步资产类型，
// 否则转债会被 preview 显示的 'stock' 带进错误的分类统计。
const BOND_CODE_PREFIXES = [
  "110",
  "111",
  "113",
  "118",
  "123",
  "127",
  "128",
  "132"
];
const canEditSymbol = computed(() =>
  String(props.row.link_warning || "").startsWith(SYMBOL_ALIAS_HINT)
);
const editingSymbol = ref(false);
const symbolDraft = ref("");

function startSymbolEdit() {
  if (!canEditSymbol.value) return;
  symbolDraft.value = String(props.row.symbol || "");
  editingSymbol.value = true;
}

function saveSymbolEdit() {
  if (!editingSymbol.value) return; // Enter 与 blur 会连发，第二次直接跳过
  const next = symbolDraft.value.trim();
  if (next) {
    // eslint-disable-next-line vue/no-mutating-props
    props.row.symbol = next;
    if (BOND_CODE_PREFIXES.some(prefix => next.startsWith(prefix))) {
      // eslint-disable-next-line vue/no-mutating-props
      props.row.type = "bond";
    }
    // 补全后撤下警示，行状态恢复正常（StatusCell 不再显示 linkWarning 档）
    // eslint-disable-next-line vue/no-mutating-props
    props.row.link_warning = "";
  }
  editingSymbol.value = false;
}

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
      <!-- #2844：display_name 由后端按「资产类型 + 收益种类」派生（券商原文不给标的的
           收益行如「基金红利拨入」，名称与代码两列本来就是空的，此前只剩「--」，
           用户看不出这笔钱是哪来的）。它只用于展示，回传给后端的仍是 name。 -->
      <span class="product-name">{{
        row.display_name || row.name || row.symbol || "--"
      }}</span>
      <span
        v-if="srcOp"
        class="product-notes"
        :title="`券商原文：${row.notes}（会写进该笔流水的备注）`"
        >{{ srcOp }}</span
      >
    </div>
    <div class="product-code-row">
      <el-input
        v-if="editingSymbol"
        v-model="symbolDraft"
        class="symbol-alias-input"
        size="small"
        autofocus
        placeholder="填写上市代码"
        @keyup.enter="saveSymbolEdit"
        @blur="saveSymbolEdit"
      />
      <el-tooltip
        v-else-if="canEditSymbol"
        content="申购代码需改为上市代码，点击补全"
        placement="top"
      >
        <button
          type="button"
          class="product-code product-code-editable"
          @click="startSymbolEdit"
        >
          # {{ row.symbol || "--" }} ✎
        </button>
      </el-tooltip>
      <span v-else class="product-code"># {{ row.symbol || "--" }}</span>
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

/* 打新建仓行：代码可补全的视觉提示（与 linkWarning 警示档配套）。
   用 <button> 承载点击而非 <span @click>：键盘可达是 #1842 守卫的硬要求，
   补 role/tabindex/@keydown 也能过，但原生 button 免费拿到 Enter/Space 与
   焦点环。故此处只把 button 的 UA 外观（边框/内边距/背景/字体）抹平，
   让它看起来仍是行内文字。 */
.product-code-editable {
  padding: 0;
  font-family: inherit;
  line-height: inherit;
  color: var(--el-color-warning);
  text-decoration: underline dashed;
  cursor: pointer;
  background: none;
  border: 0;
}

.symbol-alias-input {
  flex: 0 0 auto;
  width: 130px;
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
