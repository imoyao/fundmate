<template>
  <el-form-item label="销售机构">
    <el-select
      :model-value="modelValue"
      class="w-full"
      clearable
      filterable
      placeholder="可不选，支持汉字/别名/拼音首字母（如 ht=华泰）"
      :filter-method="filterInstitution"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <!-- 常用机构置顶分组（is_common，按 common_sort 升序）+ 全部机构（#1081）。
           自定义 filter-method：汉字原文 / 常用别名 / 拼音首字母简拼（pinyin_short）
           三路匹配，由 visibleInstitutions computed 统一过滤，空组不渲染 -->
      <el-option-group v-if="commonInstitutions.length" label="常用机构">
        <el-option
          v-for="inst in commonInstitutions"
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
            <span class="inst-option__tag">{{
              orgTypeGroupLabel(inst.org_type)
            }}</span>
          </div>
        </el-option>
      </el-option-group>
      <el-option-group v-if="otherInstitutions.length" label="全部机构">
        <el-option
          v-for="inst in otherInstitutions"
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
            <span class="inst-option__tag">{{
              orgTypeGroupLabel(inst.org_type)
            }}</span>
          </div>
        </el-option>
      </el-option-group>
    </el-select>
    <!-- 银行渠道轻提示（#1082 D8）：fund 账户选中银行类机构时缓解「卡 vs 渠道」心智混淆 -->
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
  pickOtherInstitutions,
  shouldShowBankChannelHint,
  sortCommonInstitutions
} from "./accountFormModel";

/**
 * 账户表单的「销售机构」选择器（#980 拆分自 `AccountFormFields.vue`）。
 *
 * 名称 / 别名 / 拼音三路检索、常用机构置顶、按账户类型过滤、银行渠道轻提示
 * 原先与「活期+」「费率」等字段挤在同一个 587 行文件里；拆出后判定逻辑仍只有
 * `accountFormModel.ts` 一处实现，本组件只做绑定与渲染。
 */
defineOptions({ name: "SalesInstitutionSelect" });

const props = withDefaults(
  defineProps<{
    modelValue?: number | null;
    /** 账户类型；决定可见机构类型（证券只列券商） */
    ledgerType: string;
    /** 销售机构候选列表（AMAC 名录，父组件加载传入） */
    institutions?: SalesInstitution[];
  }>(),
  { modelValue: null, institutions: () => [] }
);

const emit = defineEmits<{
  "update:modelValue": [value: number | null];
}>();

/** 销售机构下拉检索关键词（小写），由 filter-method 回写，驱动 visibleInstitutions 过滤 */
const institutionFilter = ref("");

/** 按当前账户类型 + 检索词过滤后的机构列表 */
const visibleInstitutions = computed<SalesInstitution[]>(() =>
  filterInstitutionsByKeyword(
    filterInstitutionsByLedgerType(props.institutions, props.ledgerType),
    institutionFilter.value
  )
);

const commonInstitutions = computed<SalesInstitution[]>(() =>
  sortCommonInstitutions(visibleInstitutions.value)
);

const otherInstitutions = computed<SalesInstitution[]>(() =>
  pickOtherInstitutions(visibleInstitutions.value)
);

const showBankChannelHint = computed(() =>
  shouldShowBankChannelHint(
    props.ledgerType,
    props.modelValue,
    props.institutions
  )
);

/** 自定义过滤入口：Element Plus 每次输入回调，记录关键词交由 computed 过滤 */
function filterInstitution(query: string) {
  institutionFilter.value = query.trim().toLowerCase();
}
</script>

<style scoped>
.bank-channel-hint {
  margin: var(--space-3, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
}
</style>

<!--
  销售机构选项行样式：el-select 下拉面板默认 teleport 到 body，
  scoped 样式无法命中，故用非 scoped 块 + 唯一类名（inst-option__*）避免全局污染。
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

/* 右侧类型标签：默认 Badge 形态（--bg-soft 底 + --text-secondary 字 + 胶囊圆角） */
.inst-option__tag {
  flex-shrink: 0;
  padding: 1px 8px;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}
</style>
