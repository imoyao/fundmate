<template>
  <el-form-item label="销售机构" for="sales-institution-select">
    <el-select
      id="sales-institution-select"
      :model-value="modelValue"
      class="w-full"
      clearable
      filterable
      placeholder="输入机构名 / 别名 / 首字母 / 全拼检索"
      :filter-method="filterInstitution"
      @visible-change="onDropdownVisible"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <!-- 单一列表按拼音首字母 A→Z（#2026-11-07）：旧版把常用机构按人工
           common_sort 置顶 + 其余按汉字码点序，用户按首字母找不到机构。
           自定义 filter-method 做汉字 / 别名 / 拼音简拼三路匹配。 -->
      <el-option
        v-for="inst in visibleInstitutions"
        :key="inst.id"
        :label="institutionLabel(inst)"
        :value="inst.id"
      >
        <div class="inst-option">
          <span class="inst-option__main">{{
            inst.display_name || inst.org_name
          }}</span>
          <span
            v-if="inst.display_name"
            class="inst-option__sub"
            :title="inst.org_name"
            >{{ inst.org_name }}</span
          >
          <span v-if="inst.is_common" class="inst-option__badge">常用</span>
          <span class="inst-option__tag">{{
            orgTypeGroupLabel(inst.org_type)
          }}</span>
        </div>
      </el-option>
    </el-select>

    <!-- 检索与排序说明常显：选中值会盖住 placeholder，只靠 placeholder 提示
         用户看不出这里能搜索（#2026-11-07 用户反馈「需要支持搜索」）。 -->
    <div class="inst-helper">
      <span class="inst-helper__hint">
        A→Z 排列 · 支持名称 / 别名 / 首字母 / 全拼（如 ht、zhifubao）
      </span>
      <el-checkbox
        v-model="commonOnly"
        size="small"
        aria-label="仅看常用机构"
        class="inst-helper__filter"
        >仅看常用</el-checkbox
      >
    </div>

    <!-- 银行渠道轻提示（#1082 D8）：缓解「卡 vs 渠道」心智混淆 -->
    <p v-if="showBankChannelHint" class="bank-channel-hint">
      银行渠道购买的基金记录在此；银行卡本身资产请使用银行账户管理
    </p>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { SalesInstitution } from "@/api/ledger";
import {
  filterInstitutionsByKeyword,
  filterInstitutionsByLedgerType,
  institutionLabel,
  orgTypeGroupLabel,
  pickCommonInstitutions,
  shouldShowBankChannelHint,
  sortInstitutionsByPinyin
} from "./accountFormModel";

/**
 * 账户表单的「销售机构」选择器（#980 拆分自 `AccountFormFields.vue`）。
 *
 * 判定口径（过滤 / 检索 / 排序）全部只有 `accountFormModel.ts` 一处实现，
 * 本组件只做绑定与渲染。2026-11-07 起默认排序由「常用置顶 + 码点序」
 * 改为拼音首字母 A→Z，常用机构改由标签 + 「仅看常用」开关承载。
 */
defineOptions({ name: "SalesInstitutionSelect" });

const props = withDefaults(
  defineProps<{
    modelValue?: number | null;
    /** 账户类型；决定可见机构类型（证券只列券商） */
    channelCategory: string;
    /** 销售机构候选列表（AMAC 名录，父组件加载传入） */
    institutions?: SalesInstitution[];
  }>(),
  { modelValue: null, institutions: () => [] }
);

const emit = defineEmits<{
  "update:modelValue": [value: number | null];
}>();

/** 下拉检索关键词（小写），由 filter-method 回写 */
const institutionFilter = ref("");
/** 「仅看常用」快捷筛选开关 */
const commonOnly = ref(false);

/**
 * 类型过滤 → 关键词过滤 → 常用筛选 → 拼音 A→Z 排序。
 * 排序放前端是防御性的：四个调用方的数据源不全走同一个 API 顺序。
 */
const visibleInstitutions = computed<SalesInstitution[]>(() => {
  const byType = filterInstitutionsByLedgerType(
    props.institutions,
    props.channelCategory
  );
  const byKeyword = filterInstitutionsByKeyword(
    byType,
    institutionFilter.value
  );
  return sortInstitutionsByPinyin(
    commonOnly.value ? pickCommonInstitutions(byKeyword) : byKeyword
  );
});

const showBankChannelHint = computed(() =>
  shouldShowBankChannelHint(
    props.channelCategory,
    props.modelValue,
    props.institutions
  )
);

/** 自定义过滤入口：Element Plus 每次输入回调，记录关键词交由 computed 过滤 */
function filterInstitution(query: string) {
  institutionFilter.value = query.trim().toLowerCase();
}

/** 关闭下拉时清空检索词，避免下次打开只剩上次的过滤结果 */
function onDropdownVisible(visible: boolean) {
  if (!visible) institutionFilter.value = "";
}
</script>

<style scoped>
.bank-channel-hint,
.inst-helper__hint {
  margin: var(--space-2, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
}

.inst-helper {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
}

.inst-helper__hint {
  flex: 1;
  min-width: 0;
}

.inst-helper__filter {
  flex-shrink: 0;
  margin-right: 0;
}
</style>

<!--
  el-select 下拉面板默认 teleport 到 body，scoped 样式无法命中，
  故用非 scoped 块 + 唯一类名（inst-option__*）避免全局污染。
  颜色全部走 design token，禁止硬编码 hex。
-->
<style>
.inst-option {
  display: flex;
  gap: 8px;
  align-items: baseline;
  width: 100%;
  min-width: 0;
}

/* 主文本：常用名优先（如「支付宝」） */
.inst-option__main {
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 次级文本：常用名存在时的权威全称，小字弱化 */
.inst-option__sub {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label, 13px);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 常用标记：与类型标签同形态，用 --bg-subtle 拉开层次 */
.inst-option__badge,
.inst-option__tag {
  flex-shrink: 0;
  padding: 1px 8px;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.inst-option__badge {
  background: var(--bg-subtle);
}
</style>
