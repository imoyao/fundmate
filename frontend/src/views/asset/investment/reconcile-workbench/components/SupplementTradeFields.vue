<template>
  <!--
    补录弹窗的「补一笔交易」字段区（increment 分支）。
    拆分原因：页面规模门禁（issue #980）——补手续费输入后主弹窗会顶过 400 行，
    故把整段表单字段下沉到此子组件；el-form-item 的校验收集由外层 el-form
    经 provide/inject 完成（EP 跨组件成立），rules 仍住父层，零状态重写。
    手续费只在 buy / sell 显示：存入 / 取出是银证转账，没有成交费。
    标签一律走 TRADE_FIELD_LABELS（全站唯一来源，禁止各页自造同义叫法）。
  -->
  <el-form-item label="交易类型">
    <SegmentedControl
      v-model="opTypeModel"
      :options="OP_TYPE_OPTIONS"
      block
      aria-label="交易类型"
    />
  </el-form-item>
  <el-form-item :label="TRADE_FIELD_LABELS.quantity" prop="quantity">
    <el-input-number
      v-model="quantityModel"
      :min="0"
      :precision="4"
      :controls="false"
      style="width: 100%"
      placeholder="成交了多少份 / 股"
    />
  </el-form-item>
  <el-form-item :label="TRADE_FIELD_LABELS.price" prop="avg_price">
    <el-input-number
      v-model="avgPriceModel"
      :min="0"
      :precision="4"
      :controls="false"
      style="width: 100%"
      placeholder="每份成交价（元）"
    />
  </el-form-item>
  <el-form-item
    v-if="opTypeModel === 'buy' || opTypeModel === 'sell'"
    :label="TRADE_FIELD_LABELS.fee"
  >
    <el-input-number
      v-model="feeModel"
      :min="0"
      :precision="2"
      :controls="false"
      style="width: 100%"
      placeholder="券商/平台实收，不填按 0"
    />
    <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
      含佣金、过户费等，按交割单实收金额填写；不填按 0 计，卖出少了这笔，
      已实现盈亏会偏高
    </div>
  </el-form-item>
  <el-form-item :label="TRADE_FIELD_LABELS.tradeDate">
    <el-date-picker
      v-model="tradeDateModel"
      type="date"
      value-format="YYYY-MM-DD"
      style="width: 100%"
      placeholder="这笔哪天成交的"
    />
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { TRADE_FIELD_LABELS } from "@/constants";
import SegmentedControl from "@/components/SegmentedControl/index.vue";

defineOptions({ name: "SupplementTradeFields" });

// 交易类型 4 项：选项值与后端 op_type 契约一一对应（buy/sell/deposit/withdraw），
// 禁止在别处另造同义选项表；块级铺满 + 32px 档与同表单 el-input-number 同高（design.md「Segmented」）。
const OP_TYPE_OPTIONS = [
  { label: "买入", value: "buy" },
  { label: "卖出", value: "sell" },
  { label: "存入", value: "deposit" },
  { label: "取出", value: "withdraw" }
] as const;

const props = defineProps<{
  opType: string;
  quantity: number | undefined;
  avgPrice: number | undefined;
  fee: number | undefined;
  tradeDate: string;
}>();

const emit = defineEmits<{
  "update:opType": [value: string];
  "update:quantity": [value: number | undefined];
  "update:avgPrice": [value: number | undefined];
  "update:fee": [value: number | undefined];
  "update:tradeDate": [value: string];
}>();

const opTypeModel = computed({
  get: () => props.opType,
  set: val => emit("update:opType", val)
});
const quantityModel = computed({
  get: () => props.quantity,
  set: val => emit("update:quantity", val)
});
const avgPriceModel = computed({
  get: () => props.avgPrice,
  set: val => emit("update:avgPrice", val)
});
const feeModel = computed({
  get: () => props.fee,
  set: val => emit("update:fee", val)
});
const tradeDateModel = computed({
  get: () => props.tradeDate,
  set: val => emit("update:tradeDate", val)
});
</script>
