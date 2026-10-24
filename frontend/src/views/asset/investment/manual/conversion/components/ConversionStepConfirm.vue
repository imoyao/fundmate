<script setup lang="ts">
/**
 * 第 2 步：费用与确认（#980 拆分自 ConversionForm.vue）。
 *
 * 排版按「一眼看到重点」（#2348 第三轮）：先用一句话说清这笔在做什么，
 * 再给三个数（转出 / 费用 / 净转入），其余下沉。
 * 原来 9 行等权键值对没有重点——用户得自己把结论拼出来；两个 el-input-number
 * 常驻又让复核页看起来像编辑页。
 *
 * 本组件是纯展示 + 转发：试算、费用重算、提交都在父页的 composable 里。
 * 唯一自带的状态是「折叠展开」（`showFeeDetail`）与两个费用输入框的值，
 * 它们也由父页持有，这样 `resetForm` 一处就能复位整页。
 */
import type { ConversionEstimateResult } from "@/api/positions";
import { IconifyIconOffline } from "@/components/ReIcon";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import type { RefundMode } from "../conversionFormModel";
import ConversionFigures from "./ConversionFigures.vue";
import ConversionFeeFold from "./ConversionFeeFold.vue";

defineProps<{
  estimating: boolean;
  estimate: ConversionEstimateResult | null;
  estimateError: string;
  /** 按钮可用性：垫资 / 差额未选去向都在父页算好 */
  submitValid: boolean;
  submitting: boolean;
  refundOptions: { label: string; value: "money_fund" | "account_cash" }[];
  refundMode: RefundMode;
  showFeeDetail: boolean;
  feeDirty: boolean;
  redeem: number;
  compensate: number;
}>();

const emit = defineEmits<{
  (e: "retry"): void;
  (e: "submit"): void;
  (e: "update:refundMode", value: RefundMode): void;
  (e: "update:showFeeDetail", value: boolean): void;
  (e: "update:redeem", value: number | undefined): void;
  (e: "update:compensate", value: number | undefined): void;
  (e: "feeEdit"): void;
  (e: "feeReset"): void;
}>();
</script>

<template>
  <div class="flex flex-col gap-4">
    <div
      v-if="estimating"
      class="py-10 text-center text-sm"
      :style="{ color: 'var(--text-secondary)' }"
    >
      正在试算费用与份额…
    </div>
    <template v-else-if="estimate">
      <!-- 一句话指令：动词用「换成」，主语是用户手上的钱，不是系统里的字段 -->
      <p class="confirm-sentence">
        用「{{ estimate.out.name || estimate.out.symbol }}」的
        <span class="confirm-sentence__num">{{
          estimate.out.quantity.toFixed(2)
        }}</span>
        份，换成「{{ estimate.in.name || estimate.in.symbol }}」
      </p>

      <ConversionFigures
        :out="estimate.out"
        :net-amount="estimate.net_amount"
        :in-quantity="estimate.in.quantity"
      />

      <div class="confirm-meta">
        <el-tag size="small" type="info" effect="plain">预估</el-tag>
        <span>{{ estimate.trade_date }} 提交 · T+1 确认 · T+2 可赎回</span>
      </div>

      <!-- D6 垫资拦截：submitValid 会因此变 false。原先只禁用按钮、不给原因，
           用户看到的是一个点不动的「确认转换」。 -->
      <div
        v-if="estimate.supplement.required"
        class="confirm-blocker"
        role="alert"
      >
        <IconifyIconOffline
          icon="ep:warning-filled"
          class="confirm-blocker__icon"
        />
        <span>
          转入金额超出净额 ¥{{
            estimate.supplement.amount.toFixed(2)
          }}，本平台不垫资，请回上一步调小转入金额
        </span>
      </div>

      <!-- 差额去向是阻断项（submitValid 依赖它），所以既不折叠也不降级 -->
      <div v-if="estimate.refund.amount > 0" class="confirm-refund">
        <div class="confirm-refund__head">
          <span class="confirm-refund__title">
            差额
            <span class="confirm-refund__amount"
              >¥{{ estimate.refund.amount.toFixed(2) }}</span
            >
            的去向
          </span>
          <span class="confirm-refund__req">必选</span>
        </div>
        <SegmentedControl
          :model-value="refundMode"
          :options="refundOptions"
          aria-label="差额去向"
          @update:model-value="v => emit('update:refundMode', v)"
        />
        <div class="confirm-refund__hint">
          指定转入金额小于净额时，差额不允许凭空消失
        </div>
      </div>

      <ConversionFeeFold
        :show-detail="showFeeDetail"
        :dirty="feeDirty"
        :redeem="redeem"
        :compensate="compensate"
        :estimated-redeem="estimate.out.fee_estimated?.redeem ?? 0"
        :estimated-compensate="estimate.out.fee_estimated?.compensate ?? 0"
        :in-quantity="estimate.in.quantity"
        :in-nav="estimate.in.nav"
        :in-amount="estimate.in.amount"
        @update:show-detail="v => emit('update:showFeeDetail', v)"
        @update:redeem="v => emit('update:redeem', v)"
        @update:compensate="v => emit('update:compensate', v)"
        @edit="emit('feeEdit')"
        @reset="emit('feeReset')"
      />

      <!-- 费率缺失等非阻断告警（D9：显式提示，不静默） -->
      <div
        v-for="w in estimate.warnings"
        :key="w"
        class="p-3 rounded-lg text-xs flex items-start gap-2"
        :style="{
          color: 'var(--color-warning-ink)',
          backgroundColor: 'var(--bg-soft)'
        }"
      >
        <IconifyIconOffline icon="ep:warning-filled" class="mt-0.5" />
        <span>{{ w }}</span>
      </div>
    </template>
    <div
      v-else
      class="py-10 flex flex-col items-center gap-3 text-sm"
      :style="{ color: 'var(--color-danger)' }"
    >
      <span>{{ estimateError || "试算失败" }}</span>
      <el-button size="small" @click="emit('retry')">重试</el-button>
    </div>

    <div class="confirm-actions">
      <span class="confirm-actions__note">
        实际以 T 日净值确认结果为准；提交后可在交易记录里撤销
      </span>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!submitValid"
        @click="emit('submit')"
      >
        确认转换
      </el-button>
    </div>
  </div>
</template>

<style scoped>
/* 一句话指令：整页的主语。字号只比正文大一档、行高放宽，
   两行以内读完；基金名不加粗，长名字里不会出现几段加粗在打架 */
.confirm-sentence {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 500;
  line-height: 1.65;
  color: var(--text-primary);
}

.confirm-sentence__num {
  font-variant-numeric: tabular-nums;
}

.confirm-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

/* 阻断项（垫资）：与 warnings 同一视觉族，但图标在前，读作「按钮点不动的原因」 */
.confirm-blocker {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 12px 14px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--color-warning-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-md);
}

.confirm-blocker__icon {
  margin-top: 2px;
}

/* 差额去向是阻断项，所以给它一个框：框的存在本身就是「这里有个必须做的选择」 */
.confirm-refund {
  padding: 12px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.confirm-refund__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.confirm-refund__title {
  font-size: var(--text-label);
  color: var(--text-primary);
}

.confirm-refund__amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.confirm-refund__req {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.confirm-refund__hint {
  margin-top: 8px;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

/* 底部动作行：说明在左、主按钮在右；上一步在卡头，这里只有一颗主按钮 */
.confirm-actions {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding-top: 4px;
}

.confirm-actions__note {
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
