<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑交易"
    width="520px"
    :before-close="onBeforeClose"
    @update:model-value="val => emit('update:modelValue', val)"
    @open="initForm"
    @close="resetAfterClose"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="90px"
      size="large"
      class="flex flex-col gap-4"
      :disabled="saving"
    >
      <!-- 手工编辑提示：作为弹窗内常驻提示，避免保存后弹出警告框干扰用户 -->
      <SoftBanner
        v-if="isManual"
        class="mb-1"
        variant="info"
        icon="ep:info-filled"
      >
        该记录为手工编辑，重新导入时需按新内容对账
      </SoftBanner>
      <!-- 数量/份额：基金按份额(支持小数)，股票/可转债按股|张(整数) -->
      <el-form-item :label="isFund ? '份额' : '数量'" prop="quantity">
        <el-input-number
          v-model="form.quantity"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="quantityPrecision"
          :step="quantityStep"
        />
        <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
          <template v-if="isFund">基金份额，根据金额自动反算</template>
          <template v-else>数量为整数（股 / 张）</template>
        </div>
      </el-form-item>

      <!-- 单价/净值：基金净值只读(4位)，股票价格可编辑(2位) -->
      <el-form-item :label="isFund ? '净值(元)' : '单价(元)'">
        <!-- 基金：净值不可编辑，只读展示 -->
        <el-input
          v-if="isFund"
          :model-value="
            navLoading
              ? '加载中...'
              : form.price != null
                ? Number(form.price).toFixed(4)
                : ''
          "
          readonly
          disabled
          :placeholder="navLoading ? '加载中...' : '--'"
        >
          <template #append>元/份</template>
        </el-input>
        <!-- 股票：价格可编辑，2位小数 -->
        <el-input-number
          v-else
          v-model="form.price"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="2"
          :step="0.01"
          placeholder="0.00"
        />
      </el-form-item>

      <!-- 金额：自动计算 = 数量 * 单价 + 手续费，可手动覆盖 -->
      <el-form-item label="金额(元)">
        <el-input-number
          v-model="form.amount"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="2"
          :step="0.01"
          placeholder="0.00"
        />
        <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
          <span v-if="isFund">金额为权威数据，份额自动反算，可手动修改</span>
          <span v-else>自动计算：数量 × 单价 + 手续费，可手动修改</span>
        </div>
      </el-form-item>

      <!-- 手续费：2 位小数 -->
      <el-form-item label="手续费(元)">
        <el-input-number
          v-model="form.fee"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="2"
          :step="0.01"
          placeholder="0.00"
        />
      </el-form-item>

      <!-- 交易日期 + 15:00前/后（基金） -->
      <el-form-item label="交易日期" prop="trade_date">
        <div class="flex items-center gap-3 w-full">
          <!-- 日期框外层自带弹性：DatePicker 是 inheritAttrs:false，写它身上的
               `class="flex-1"` 落不到 DOM。 -->
          <div class="min-w-0 flex-1">
            <el-date-picker
              v-model="form.trade_date"
              type="date"
              style="width: 100%"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              clearable
              :disabled-date="disabledDate"
            />
          </div>
          <TradeSlotSwitch v-if="isFund" v-model="isAfter15" />
        </div>
        <div
          v-if="isFund"
          class="text-xs mt-1"
          style="color: var(--text-tertiary-ink)"
        >
          预计确认日：{{ confirmDateDisplay || "计算中..." }}
        </div>
      </el-form-item>

      <!-- 备注 -->
      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          placeholder="选填"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <!-- 取消也走守卫：`before-close` 只拦关闭按钮 / ESC / 点遮罩，程序化 close 走不到它（#1835） -->
      <el-button :disabled="saving" @click="requestClose">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 编辑交易弹窗。#980 拆分后本文件只剩「视图 + 接线」：
// 联动与保存逻辑在 transactionEdit/useTransactionEditForm.ts，
// 纯口径（反算 / 类型兜底 / 快照）在 transactionEdit/transactionEditModel.ts。
import TradeSlotSwitch from "@/components/TradeSlotSwitch/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import { useTransactionEditForm } from "./transactionEdit/useTransactionEditForm";

const props = defineProps<{
  modelValue: boolean;
  transaction: any;
  assetType?: string;
  /** 基金代码（用于自动拉取净值，可从 positionData 或交易记录获取） */
  symbol?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [data: any];
}>();

const {
  saving,
  formRef,
  form,
  isAfter15,
  confirmDateDisplay,
  navLoading,
  isManual,
  isFund,
  quantityPrecision,
  quantityStep,
  disabledDate,
  rules,
  initForm,
  resetAfterClose,
  onBeforeClose,
  requestClose,
  handleSave
} = useTransactionEditForm({
  transaction: () => props.transaction,
  symbol: () => props.symbol,
  assetTypeOverride: () => props.assetType,
  onSaved: data => emit("saved", data),
  onClose: () => emit("update:modelValue", false)
});
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}

/* 去掉 el-form-item 默认 margin-bottom，间距统一由 gap-4 控制 */
:deep(.el-form-item) {
  margin-bottom: 0;
}

/* 输入框 / 数字输入 / 日期选择器：视觉全部走 element-plus.scss 的
   「输入基线（#1772）」（底色、边框三态、圆角、焦点环），本文件不再
   用 :deep 覆盖 wrapper / textarea 内层的同一件事。
   本表单（size=large）的控件高度是 40px，用高度令牌表达。 */
.el-form {
  --input-height: 40px;
}

/* el-input-number controls=false 后文字默认居中，强制左对齐。
   用原生 input 元素匹配（而非 .el-input__inner），既避开 EP 同特异性的
   `.el-input-number .el-input__inner{text-align:center}`，也避免本文件
   再次命中「三个禁改选择器」。 */
:deep(.el-input-number input) {
  text-align: left;
}

/* 日期选择器：强制 100% 宽度，与数字输入框等宽（高度由上面的高度令牌接管） */
:deep(.el-date-editor.el-input) {
  width: 100% !important;
}

/* 主按钮物理反馈 */
:deep(.el-button--primary) {
  height: 40px;
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.15s;
}

:deep(.el-button--primary:active) {
  box-shadow: none !important;
  transform: translateY(1px);
}

/* 校验错误样式 */
:deep(.el-form-item__error) {
  padding-top: 2px;
  font-size: 0.75rem;

  /* `--el-color-danger` 是 Element Plus 默认 #f56c6c（对白底 2.90:1，不达 AA）→ 用本项目语义危险色（4.74:1） */
  color: var(--color-danger);
  transition: none;
}
</style>
