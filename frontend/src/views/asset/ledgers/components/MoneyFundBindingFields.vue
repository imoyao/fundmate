<template>
  <el-form-item label="活期+">
    <el-select
      :model-value="modelValue"
      class="w-full"
      clearable
      filterable
      remote
      reserve-keyword
      :remote-method="searchMoneyFund"
      :loading="fundSearching"
      placeholder="搜索货币基金，如「余额宝」「水星」"
      @update:model-value="onMoneyFundChange"
    >
      <!-- 全量搜索 + 选择时限制：后端 is_money_fund 为三态，
           false（明确非货基）禁用并标注；true / null（未知）均可选，
           避免类型标注缺失的券商业内现金管理产品（如 026029）被误筛。 -->
      <el-option
        v-for="f in effectiveFundOptions"
        :key="f.code"
        :label="f.name ? `${f.name}（${f.code}）` : f.code"
        :value="f.code"
        :disabled="f.is_money_fund === false"
      >
        <span>{{ f.name ? `${f.name}（${f.code}）` : f.code }}</span>
        <span v-if="f.is_money_fund === false" class="mf-option-tag"
          >非货币基金</span
        >
      </el-option>
    </el-select>
    <p class="field-hint">
      绑定后，卖出 /
      赎回回款可自动申购该产品（类似「余额宝」）。支持场外货币基金与券商渠道现金管理产品
    </p>
  </el-form-item>

  <el-form-item label="自动申购">
    <el-switch
      :model-value="autoPurchase"
      :disabled="!modelValue"
      @update:model-value="onAutoPurchaseChange"
    />
    <p class="field-hint">
      {{
        modelValue
          ? "开启后，卖出 / 赎回回款将自动申购已绑定的活期+"
          : "请先绑定活期+，再开启自动申购"
      }}
    </p>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { searchFunds, type FundSearchItem } from "@/api/funds";

/**
 * 账户表单的「活期+」绑定与自动申购（#980 拆分自 `AccountFormFields.vue`，#1137）。
 *
 * 入参/出参统一用基金代码（搜索结果即 code），存储由后端转 funds.id。
 * 两个 form-item 放一起，是因为「自动申购」的可用性完全由绑定值决定
 * （未绑定则开关禁用 + 走另一句说明），拆开会让这条联动跨组件。
 */
defineOptions({ name: "MoneyFundBindingFields" });

const props = withDefaults(
  defineProps<{
    /** 绑定的活期+基金代码（null=未绑定） */
    modelValue?: string | null;
    /** 绑定产品名称（出参回显用；远程搜索未触发时也能显示名称而非裸代码） */
    fundName?: string | null;
    /** 卖出/赎回回款是否自动申购绑定的活期+（默认关闭） */
    autoPurchase?: boolean;
  }>(),
  { modelValue: null, fundName: null, autoPurchase: false }
);

const emit = defineEmits<{
  "update:modelValue": [value: string | null];
  "update:autoPurchase": [value: boolean];
}>();

/** 远程搜索中的候选（仅当次搜索结果，不缓存全量） */
const fundOptions = ref<FundSearchItem[]>([]);
const fundSearching = ref(false);
/** 当前已选活期+的名称（用户从搜索结果中选中时回写）。
 *  独立于 props.fundName：换绑后后者可能仍是旧产品名，
 *  用本值保证「重新选择产品」时下拉/回显都显示当前所选产品的名称而非裸代码（#交互修复）。 */
const selectedMoneyFundName = ref<string | null>(null);

/** 实际候选项：并入当前已绑定项，保证编辑回显时下拉里存在该选项（显示名称而非裸代码） */
const effectiveFundOptions = computed<FundSearchItem[]>(() => {
  const list = [...fundOptions.value];
  const bound = props.modelValue;
  if (bound && !list.some(o => o.code === bound)) {
    // 优先用本次搜索命中的名称（用户刚选过，最准），回退到出参名称，最后兜底裸代码。
    // 注：不能用 props.fundName 一项兜底——换绑后它可能仍是旧产品的名称，
    // 会导致「选了 B 却显示 A 的名字 / 或裸代码」的 bug（#交互修复）。
    list.unshift({
      code: bound,
      name: selectedMoneyFundName.value || props.fundName || bound,
      type: "货币基金",
      subscription_rate: 0
    });
  }
  return list;
});

async function searchMoneyFund(query: string) {
  const kw = (query ?? "").trim();
  if (!kw) {
    fundOptions.value = [];
    return;
  }
  fundSearching.value = true;
  try {
    const res = await searchFunds(kw);
    const list = ((res as any)?.data ?? []) as FundSearchItem[];
    // 全量搜索 + 选择时限制（#活期+ 扩源）：
    // 后端 is_money_fund 已升级为三态——true=货基 / false=明确非货基 / null=类型未知。
    // 搜索阶段**不再过滤**，全部命中项都进下拉；能否选中交给 el-option 的
    // :disabled="f.is_money_fund === false" 控制。
    // 不在搜索阶段剔除的原因：本地库 fund_type_id 有 88.7% 为空，此前按
    // `fund_type_id == 6` 判定会把一批真货基误判为非货基而彻底搜不到——
    // 典型如 026029 银河水星现金添利货币（券商渠道现金管理产品，
    // 库内已同步 120 天万份收益，收益口径与场外货基一致）。
    fundOptions.value = list;
  } catch {
    fundOptions.value = [];
  } finally {
    fundSearching.value = false;
  }
}

function onMoneyFundChange(val: string | null) {
  emit("update:modelValue", val ?? null);
  // 选中时回写名称（优先取搜索结果里的权威名），供 effectiveFundOptions 兜底展示用，
  // 避免重新打开下拉（远程搜索列表被清空）时回显成裸代码。
  if (val) {
    const hit = fundOptions.value.find(o => o.code === val);
    selectedMoneyFundName.value = hit?.name ?? props.fundName ?? null;
  } else {
    selectedMoneyFundName.value = null;
  }
  // 解绑时联动关闭开关，避免残留一个无法生效的开关（后端亦会强制关闭）
  if (!val) {
    emit("update:autoPurchase", false);
  }
}

function onAutoPurchaseChange(val: boolean) {
  emit("update:autoPurchase", !!val);
}
</script>

<style scoped>
/* 活期+绑定与自动申购的说明文字（#1137）：辅助层级，--text-tertiary */
.field-hint {
  margin: var(--space-3, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

/* 活期+ 下拉中的「非货币基金」标注（全量搜索 + 选择时限制）：
   与产品名同行、弱化显示；禁用态由 el-option 自身置灰，此处只做类型提示，
   让用户理解「为什么这项选不了」，而非单纯消失不见。 */
.mf-option-tag {
  padding: 0 6px;
  margin-left: var(--space-3, 8px);
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-sm, 4px);
}
</style>
