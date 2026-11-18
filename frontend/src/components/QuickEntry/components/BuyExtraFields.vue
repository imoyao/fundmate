<template>
  <!-- 配置目标 + 备注（#980 拆自 BuyForm.vue）。
       两者都是「本笔交易的补充信息」，与价格/数量/金额/手续费那组核心字段不同层级，
       故独立成块；也是 BuyForm 回落 400 行门禁的那部分行数。状态仍住父层。 -->
  <el-form-item label="配置目标" prop="allocation">
    <el-select
      v-model="allocationModel"
      class="w-full"
      style="display: block; width: 100%"
      placeholder="选择配置目标"
    >
      <el-option
        v-for="opt in ALLOCATION_OPTIONS"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>
  </el-form-item>

  <el-form-item :label="TRADE_FIELD_LABELS.notes">
    <el-input
      v-model="notesModel"
      type="textarea"
      :rows="2"
      placeholder="补充交易理由（选填）"
      style="width: 100%"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ALLOCATION_OPTIONS, TRADE_FIELD_LABELS } from "@/constants";

const props = defineProps<{
  allocation: string;
  notes: string;
}>();
const emit = defineEmits<{
  "update:allocation": [value: string];
  "update:notes": [value: string];
}>();

const allocationModel = computed({
  get: () => props.allocation,
  set: val => emit("update:allocation", val)
});
const notesModel = computed({
  get: () => props.notes,
  set: val => emit("update:notes", val)
});
</script>
