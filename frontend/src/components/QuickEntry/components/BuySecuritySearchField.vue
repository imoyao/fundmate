<template>
  <!-- 证券/基金搜索：按账户类型切到基金或证券接口，空结果给手填兜底。
       #980 拆分自 BuyForm.vue，搜索状态与远程查询整体搬进本组件。 -->
  <el-form-item :label="searchLabel" prop="symbol">
    <el-select
      v-model="selectedModel"
      value-key="symbol"
      remote
      filterable
      reserve-keyword
      :placeholder="searchPlaceholder"
      :remote-method="remoteSearch"
      :loading="searchLoading"
      clearable
      class="w-full"
      style="display: block; width: 100%"
      @change="onChange"
    >
      <el-option
        v-for="item in securityOptions"
        :key="item.symbol"
        :label="`${item.symbol} ${item.name} (${item.type_label || item.type})`"
        :value="item"
      />
      <template #empty>
        <div
          class="text-center py-4 text-sm"
          style="color: var(--text-tertiary-ink)"
        >
          <template v-if="!searchLoading">{{ emptyHint }}</template>
        </div>
      </template>
    </el-select>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  useSecuritySearch,
  type SecurityOption
} from "@/components/QuickEntry/composables/useSecuritySearch";

const props = defineProps<{
  /** 当前账户类型（fund / bank / stock），决定搜基金还是搜证券 */
  ledgerType?: string;
  modelValue: SecurityOption | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: SecurityOption | null];
  /** 选中/清空：父层据此回填价格与手续费预设 */
  select: [option: SecurityOption | null];
}>();

const selectedModel = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

const searchLabel = computed(() => {
  const t = props.ledgerType;
  return t === "fund" || t === "bank" ? "基金" : "证券";
});
const searchPlaceholder = computed(() =>
  props.ledgerType === "fund" || props.ledgerType === "bank"
    ? "输入基金代码或名称"
    : "输入股票/ETF代码或名称"
);
const emptyHint = computed(
  () => `还没有${searchLabel.value}持仓？去「全面盘点」导入交割单吧 >`
);

const { searchLoading, securityOptions, remoteSearch, reset } =
  useSecuritySearch(() => props.ledgerType ?? "");

function onChange(option: unknown) {
  emit("select", (option as SecurityOption | null) || null);
}

// 账户类型切换时父层要求清掉旧选项（上一个账户的品类，留着会误导）
defineExpose({ reset });
</script>
