<template>
  <!--
    补录弹窗的「补一笔交易」字段区（increment 分支）。
    拆分原因：页面规模门禁（issue #980）——补手续费输入后主弹窗会顶过 400 行，
    故把整段表单字段下沉到此子组件；el-form-item 的校验收集由外层 el-form
    经 provide/inject 完成（EP 跨组件成立），rules 仍住父层，零状态重写。
    手续费只在 buy / sell 显示：存入 / 取出是银证转账，没有成交费。
    标签一律走 TRADE_FIELD_LABELS（全站唯一来源，禁止各页自造同义叫法）。
    字段顺序对齐全站交易录入（QuickEntry BuyForm/SellForm）：先日期、后量价费。
    「卖出全仓」是单值快捷填充（按流水算的份额），不是比例档位——分工见 design.md。
  -->
  <el-form-item label="交易类型">
    <SegmentedControl
      v-model="opTypeModel"
      :options="OP_TYPE_OPTIONS"
      block
      aria-label="交易类型"
    />
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
  <el-form-item :label="TRADE_FIELD_LABELS.quantity" prop="quantity">
    <div class="supplement-fields__quantity">
      <el-input-number
        v-model="quantityModel"
        :min="0"
        :precision="4"
        :controls="false"
        class="supplement-fields__quantity-input"
        placeholder="成交了多少份 / 股"
      />
      <el-tooltip
        v-if="opTypeModel === 'sell'"
        :content="sellAllTitle"
        placement="top"
      >
        <span class="supplement-fields__quantity-anchor">
          <el-button :disabled="!sellAllReady" @click="fillSellAll">
            卖出全仓
          </el-button>
        </span>
      </el-tooltip>
    </div>
    <div
      v-if="opTypeModel === 'sell' && !sellAllReady"
      class="text-xs mt-1"
      style="color: var(--text-tertiary-ink)"
    >
      这条差异没有按流水算出的份额，核对流水后直接手填数量
    </div>
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
</template>

<script setup lang="ts">
import { computed } from "vue";
import { TRADE_FIELD_LABELS } from "@/constants";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { reconQuantity } from "../utils/reconDisplay";

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
  /** 按流水算的份额（差异行 expected_value，单位份）；空或 ≤0 时「卖出全仓」降级禁用 */
  expectedQuantity: number | null;
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

/**
 * 卖出全仓：单值快捷填充（不是 QuickRatioPicker 的比例档位，分工见 design.md）。
 * 数值 = 差异行 expected_value（按流水算的份额）；缺失 / ≤0 时禁用并给一句说明，
 * 绝不静默填 0——那会写成「卖了 0 份」。点击后仍可手改，不锁输入框、
 * 不高亮成「已选比例」；按钮走次按钮语言，不抢「补上这笔」的主按钮位。
 */
const sellAllReady = computed(
  () =>
    typeof props.expectedQuantity === "number" &&
    Number.isFinite(props.expectedQuantity) &&
    props.expectedQuantity > 0
);
const sellAllTitle = computed(() =>
  sellAllReady.value
    ? // 份额展示一律走 reconQuantity（千分位 + 份），不要自己拼数字
      `按流水填入 ${reconQuantity(props.expectedQuantity)}`
    : "这条差异没有按流水算出的份额，需手填数量"
);
function fillSellAll(): void {
  const qty = props.expectedQuantity;
  if (typeof qty !== "number" || !Number.isFinite(qty) || qty <= 0) return;
  emit("update:quantity", qty);
}
</script>

<style scoped>
/* 数量行 = 输入框 +（卖出时的）全仓快捷；两者同高 32px，快捷按钮次级语言不抢主按钮焦点 */
.supplement-fields__quantity {
  display: flex;
  gap: var(--space-compact);
  align-items: center;
  width: 100%;
}

.supplement-fields__quantity-input {
  flex: 1;
  min-width: 0;
}
</style>
