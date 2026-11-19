<template>
  <el-form-item label="产品名称">
    <el-input
      v-model="nameModel"
      placeholder="如：招银理财朝朝宝（用于展示与搜索）"
      maxlength="100"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";

/**
 * 银行理财手填项的产品名称（#931 / D121）。
 *
 * 为什么需要单独一栏：`symbol` 存的是**理财登记编码**（银登中心全市场唯一，D121），
 * 而手填时用户先输进去的也是那串编码。若没有这一栏，落库后 `name` 就等于
 * `Z7xxxxxxxx` 这样的码，持仓列表里根本认不出是哪只产品——而产品名正是
 * 后端搜索源唯一的可读匹配键（`services/asset_search._search_bank_wealth`）。
 *
 * 只在「手填的银行理财」这一种情形出现：从历史持仓搜到的产品已经带着正确名称，
 * 再让用户改一遍是多余的表单项。
 */
const props = defineProps<{ name: string }>();
const emit = defineEmits<{ "update:name": [value: string] }>();

const nameModel = computed({
  get: () => props.name,
  set: val => emit("update:name", val)
});
</script>
