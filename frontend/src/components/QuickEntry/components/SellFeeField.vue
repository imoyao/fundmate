<template>
  <!--
    卖出费用（#980 拆分自 SellForm.vue；阶段 0 起对**全品种**可见）。

    为什么股票也要这一栏：卖出盈亏（后端 `compute_sell_realized_cents`）与
    「回款自动申购净额」都按 `fee` 结转。此前这里用 `v-if="form.type === 'fund'"`
    只给基金，股票卖出永远记不到费用 ⇒ 已实现盈亏虚高、回款多算一笔。
    基金仍保留「查询费率」（按持有天数匹配赎回费率）；股票/ETF 按交割单实收金额手填。
  -->
  <el-form-item :label="TRADE_FIELD_LABELS.fee" prop="fee">
    <div class="flex flex-col gap-2 w-full">
      <div class="flex items-center gap-3 w-full">
        <el-input-number
          v-model="feeModel"
          class="flex-1"
          :controls="false"
          :precision="2"
          :min="0"
          :placeholder="
            type === 'fund'
              ? '输入手续费金额'
              : '券商实际收取的费用（不确定可留 0）'
          "
          @change="emit('fee-manual-change')"
        />
        <el-button v-if="type === 'fund'" @click="emit('open-rate-dialog')"
          >查询费率</el-button
        >
      </div>
    </div>
    <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
      <span v-if="type === 'fund'">按持仓天数自动匹配费率，可手动修改</span>
      <span v-else
        >含佣金、印花税、过户费等，按交割单实收金额填写；不填则按 0
        计，卖出盈亏会偏高</span
      >
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { TRADE_FIELD_LABELS } from "@/constants";

const props = defineProps<{
  fee: number | undefined;
  /** 品类：决定是否展示「查询费率」与提示文案 */
  type: string;
}>();
const emit = defineEmits<{
  "update:fee": [value: number | undefined];
  /** 用户手改过费用：父层据此停止按费率覆盖 */
  "fee-manual-change": [];
  "open-rate-dialog": [];
}>();

const feeModel = computed({
  get: () => props.fee,
  set: val => emit("update:fee", val)
});
</script>
