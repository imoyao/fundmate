<!--
  PositionMaturityDialog · 持仓「到期日」编辑弹窗（#931 / D121）

  为什么不是一个完整的「编辑持仓」弹窗：本仓目前没有这样东西，而到期日是唯一一个
  既不属于买入表单、也没有任何入口的字段（PR4 只开了 API）。表单侧 `BuyForm.vue` 已到
  399/400 行体量门禁，塞不进去；逆回购的到期日更是买入之后才会被修正的值「录错了」，
  本来就该在持仓上改。

  口径说明由 `positionMaturity.maturityHint` 按品类分叉：逆回购到期转现金会影响总资产
  分类，银行理财只记录——两类共用一句文案会误导其中一类。
-->
<template>
  <el-dialog
    :model-value="visible"
    title="到期日"
    width="420px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <p class="dialog-product">
      {{ name || "--" }}<span v-if="symbol">（{{ symbol }}）</span>
    </p>
    <el-date-picker
      v-model="value"
      type="date"
      value-format="YYYY-MM-DD"
      placeholder="选择到期日"
      clearable
      style="width: 100%"
    />
    <p class="dialog-hint">{{ maturityHint(assetType) }}</p>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { maturityHint } from "./positionMaturity";

const props = withDefaults(
  defineProps<{
    visible: boolean;
    /** 产品名（弹窗里回显，避免用户记错在改哪一条） */
    name?: string | null;
    symbol?: string | null;
    /** 品类：决定提示语与可编辑性 */
    assetType?: string | null;
    /** 当前值（`YYYY-MM-DD`），空 = 未设 */
    maturityDate?: string | null;
    loading?: boolean;
  }>(),
  { name: "", symbol: "", assetType: "", maturityDate: null, loading: false }
);

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  /** 提交：空串归一成 null（= 清空），后端 `parse_maturity_date` 认这个语义 */
  (e: "submit", value: string | null): void;
}>();

const value = ref<string>("");

// 每次打开都从行上重置：直接复用上次的值会让「这条没设、那条设了」互相污染
watch(
  () => [props.visible, props.maturityDate] as const,
  ([visible]) => {
    if (visible) value.value = props.maturityDate ?? "";
  },
  { immediate: true }
);

function submit() {
  emit("submit", value.value || null);
}
</script>

<style lang="scss" scoped>
.dialog-product {
  margin: 0 0 12px;
  font-weight: 600;
}

.dialog-hint {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
