<template>
  <el-select
    ref="searchSelectRef"
    v-model="selected"
    value-key="symbol"
    remote
    filterable
    reserve-keyword
    placeholder="输入名称搜索，如「远足」「沪深300」"
    :remote-method="remoteSearch"
    :loading="searchLoading"
    class="w-full asset-search"
    popper-class="add-asset-option-popper"
    @change="onChange"
    @blur="onSearchBlur"
    @visible-change="onSearchDropdownToggle"
  >
    <el-option
      v-for="item in searchResults"
      :key="item.symbol"
      :label="item.name"
      :value="item"
    >
      <div class="asset-option">
        <span class="asset-option__name" :title="rowColumns(item).name">{{
          rowColumns(item).name
        }}</span>
        <span
          v-if="rowColumns(item).sub"
          class="asset-option__sub"
          :title="rowColumns(item).sub"
          >{{ rowColumns(item).sub }}</span
        >
        <span
          class="asset-option__type"
          :class="`asset-option__type--${rowColumns(item).typeKey}`"
          >{{ rowColumns(item).type }}</span
        >
      </div>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
// 搜索框（关键字输入 → 远程搜索 → 下拉里按「名称 | 次要锚点 | 类型」三列展示）。
// #980 拆分自 AddToWatchlistModal.vue；行取值在 ./assetOptionColumns.ts。
import { computed, nextTick, ref, type ComponentPublicInstance } from "vue";
import { useAssetSearch } from "@/composables/useAssetSearch";
import { rowColumns, type SearchAssetOption } from "./assetOptionColumns";

const props = defineProps<{
  modelValue: SearchAssetOption | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: SearchAssetOption | null];
  /** 用户完成一次选择（父层据此查重并重置分组/标签） */
  change: [value: SearchAssetOption | null];
}>();

const selected = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const searchLoading = ref(false);
const searchResults = ref<SearchAssetOption[]>([]);
const searchSelectRef = ref<ComponentPublicInstance | null>(null);
/** 最近一次真正发起远程搜索的关键字（#2214 回填用，见 restoreSearchKeyword） */
const searchKeyword = ref("");

// #1286：搜索改走全局唯一入口 useAssetSearch（后端聚合端点，五品种一次扇出），
// 本弹窗不再直调 securities/funds 搜索 API。
const { search: runUnifiedSearch, results: unifiedResults } = useAssetSearch();

const remoteSearch = async (query: string) => {
  // 关键字留档：下拉关闭后 EP 会清空输入框显示值，回填靠这份副本（#2214）
  searchKeyword.value = query || "";
  if (!query) {
    searchResults.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    await runUnifiedSearch(query);
    // 统一信封 → 弹窗选项（code 与 symbol 同值，兼容既有模板与提交流程）
    searchResults.value = unifiedResults.value.map(item => ({
      symbol: item.code,
      name: item.name,
      market: item.market ?? "",
      type: item.type,
      venue: item.venue ?? "",
      // extra 必须整段透传：平台（投顾组合）、主理人、所属公司（经理）都靠它展示
      extra: item.extra,
      searchType: item.type === "fund" ? ("fund" as const) : ("sec" as const)
    }));
  } finally {
    searchLoading.value = false;
  }
};

// ── #2214：下拉关闭 / 失焦后保留搜索关键字 ──
// 根因：el-select 在下拉收起时（watch expanded → false）会把内部显示值
// states.inputValue 清空；单选且未选中任何标的时，输入框就退回 placeholder，
// 用户刚敲的关键字凭空消失——「搜了没结果、想回来改两个字」这条路径直接断掉。
// （reserve-keyword 只作用于多选分支，挡不住这次清空。）
// 对策：关闭后把关键字副本回填进 select 的显示值。已选中标的时显示由
// selectedLabel 接管，不回填，否则会盖住资产名。
function restoreSearchKeyword() {
  const el = searchSelectRef.value as unknown as {
    states?: { inputValue?: string };
  } | null;
  if (!el?.states) return;
  // 选中态 / 无关键字：保持 EP 默认显示
  if (props.modelValue || !searchKeyword.value) return;
  el.states.inputValue = searchKeyword.value;
}

/** 下拉收起（点击外部、ESC、无结果失焦）后回填；nextTick 保证排在 EP 清空之后 */
function onSearchDropdownToggle(open: boolean) {
  if (open) return;
  nextTick(restoreSearchKeyword);
}

/** 失焦路径兜底：EP 的 click-outside 是在 nextTick 里触发 blur 的 */
function onSearchBlur() {
  nextTick(restoreSearchKeyword);
}

const onChange = (option: SearchAssetOption | null) => {
  emit("change", option);
};

/** 关闭后清空内部状态（父层 resetForm 调用；弹窗 destroy-on-close 时本就不存在，故可选） */
function reset() {
  searchResults.value = [];
  searchKeyword.value = "";
}

defineExpose({ reset });
</script>

<style scoped>
/* ── 搜索结果项：主行三列（名称主视觉 | 次要锚点灰 | 类型配色最右），全部一行平铺。
   注意：下拉浮层被 teleport 到 body，这里只负责「行内结构」，浮层容器样式
   （高度、行高、hover）在文件末尾的非 scoped 块中按 popper-class 限定。 */
.asset-option {
  display: flex;
  gap: 10px;
  align-items: center;
  width: 100%;
  min-width: 0;
}

/* 名称：所有品种统一主视觉（加粗、主色、占满左列、超长省略）。
   方案 A：名称恒为主视觉，次要锚点（代码/平台/主理人）落到右侧灰字，
   类型 pill 固定最右——混合列表里每行结构完全一致。 */
.asset-option__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  font-weight: 600;
  line-height: 20px;
  color: var(--text-primary);
  white-space: nowrap;
}

/* 次要锚点：编码 / 平台·主理人 / 市场；灰色小字、不占空间、无则不渲染 */
.asset-option__sub {
  flex: 0 0 auto;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 20px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

.asset-option__type {
  flex-shrink: 0;
  padding: 0 6px;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-secondary);
  background-color: var(--bg-soft);
  border-radius: var(--radius-pill);
}

/* 类型 pill 按品种配色：色值来自 colors.css / dark.scss 的 `--asset-cat-*`
   唯一真相源（莫兰迪文字色 + 18% 同 hue 底，12 品种互不撞色，暗色同名覆盖）；
   未知品种走默认灰。 */
.asset-option__type--fund {
  color: var(--asset-cat-fund);
  background-color: var(--asset-cat-fund-bg);
}

.asset-option__type--stock {
  color: var(--asset-cat-stock);
  background-color: var(--asset-cat-stock-bg);
}

.asset-option__type--etf {
  color: var(--asset-cat-etf);
  background-color: var(--asset-cat-etf-bg);
}

.asset-option__type--index {
  color: var(--asset-cat-index);
  background-color: var(--asset-cat-index-bg);
}

.asset-option__type--bond {
  color: var(--asset-cat-bond);
  background-color: var(--asset-cat-bond-bg);
}

.asset-option__type--crypto {
  color: var(--asset-cat-crypto);
  background-color: var(--asset-cat-crypto-bg);
}

.asset-option__type--portfolio {
  color: var(--asset-cat-portfolio);
  background-color: var(--asset-cat-portfolio-bg);
}

.asset-option__type--manager {
  color: var(--asset-cat-manager);
  background-color: var(--asset-cat-manager-bg);
}

.asset-option__type--money_fund {
  color: var(--asset-cat-money-fund);
  background-color: var(--asset-cat-money-fund-bg);
}

.asset-option__type--reverse_repo {
  color: var(--asset-cat-reverse-repo);
  background-color: var(--asset-cat-reverse-repo-bg);
}
</style>

<!-- 下拉浮层样式必须放在**非 scoped** 块：el-select 的 dropdown 被 teleport 到 body，
     scoped 属性与 :deep() 都命中不到浮层 DOM。此处以 popper-class 限定作用域，
     只影响本弹窗的搜索下拉，不污染其它 el-select。 -->
<style>
/* EP 默认 .el-select-dropdown__item 是 height / line-height: 34px 的「单行」容器，
   自绘的两行内容会贴顶，视觉上就是「文字没有上下居中」（用户实测反馈）。
   这里把高度交给内容（height: auto + 上下 padding）并重置 line-height: normal，
   同时显式 flex + align-items: center 保证行内内容垂直居中；
   min-height 从 48px 降到 36px，单行选项不再显得过于高挑。 */
.add-asset-option-popper .el-select-dropdown__item {
  display: flex;
  align-items: center;
  height: auto;
  min-height: 36px;
  padding: 8px 12px;
  line-height: normal;
  white-space: normal;
}

.add-asset-option-popper .el-select-dropdown__item:not(.is-disabled):hover {
  background-color: var(--bg-hover);
}

/* 选中态回到品牌软底（与全站「软按钮」语言一致），不用 EP 默认的实心主色文字 */
.add-asset-option-popper .el-select-dropdown__item.is-selected {
  font-weight: 400;
  color: var(--text-primary);
  background-color: var(--brand-100);
}
</style>
