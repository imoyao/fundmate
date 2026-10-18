<script setup lang="ts">
/**
 * QuickRatioPicker · 份额快捷档位（全部 / 1/4 / 1/3 / 1/2 / 3/4）。
 *
 * ## 为什么要有这个组件（#2339 收编尾单）
 *
 * 同一件事（「按比例快速填份额」）在仓里有两套实现：
 *
 * | 位置 | 档位表 | 外观 |
 * |---|---|---|
 * | `QuickEntry/SellForm.vue` | `SELL_QUICK_RATIOS`（全部/1/4/1/3/1/2/3/4） | 5 个 `el-button` + 自写 `.quick-ratio-btn` |
 * | `manual/ConversionForm.vue` | **自己又声明了一份** `TRANSFER_QUICK_RATIOS`（25%/50%/75%/全部） | `SegmentedControl` |
 *
 * 取整算法本来就是共用的（`calcSellQuantityByRatio`），漂的是**档位表与外观**：
 * 一边写分数、一边写百分比，「全部」一边在首位、一边在末位。
 *
 * ## 统一口径（本组件即唯一实现）
 *
 * - **档位表只有一份**：`utils/trading.ts` 的 `SELL_QUICK_RATIOS`，标签用**分数**
 *   （份额语义更贴：1/4 就是「四分之一份额」；百分比是金额语义）。
 * - **「全部」放首位**：清仓是高频动作，行业 App（天天基金 / 支付宝）都这么排，
 *   沿用 `SELL_QUICK_RATIOS` 既有顺序，不另起一套。
 * - **选中态是软按钮**（`SegmentedControl`），不用实底——#1731 裁决，避免与主按钮撞脸。
 * - **高亮由数值反算**，不用内部 state：用户手改份额后自动掉高亮，不会出现
 *   「按钮还亮着、数字已经不是那个比例」的假象。
 *
 * ## 反算必须复用同一个取整函数
 *
 * 份额按 1 份向下取整（基金）或按步长取整（股票），浮点比值并不等于
 * `0.25 × 持仓`。#2336 在 `ConversionForm` 里已经踩过一次（点完 25% 被判成未命中），
 * 所以这里也用 `calcSellQuantityByRatio` 反算，不要自己乘。
 */
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { SELL_QUICK_RATIOS, calcSellQuantityByRatio } from "@/utils/trading";

defineOptions({ name: "QuickRatioPicker" });

const props = withDefaults(
  defineProps<{
    /** 当前份额（用于反算高亮档位）；`null` / `<=0` = 无高亮 */
    modelValue?: number | null;
    /** 分母：可用 / 持有份额 */
    total: number;
    /** 资产类型，决定取整语义（`fund` 按 1 份；股票按步长） */
    type?: string;
    /** 最小交易单位；股票/ETF 传 `stepForSecurity`，基金传 1 */
    step?: number;
    disabled?: boolean;
    /** 读屏标签，同页多组时用于区分 */
    ariaLabel?: string;
  }>(),
  {
    modelValue: null,
    type: "fund",
    step: 1,
    disabled: false,
    ariaLabel: "快捷比例"
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", quantity: number): void;
  /** 同时抛出命中的比例，供调用方做「全部 = 精确清算」这类附加语义 */
  (e: "select", payload: { ratio: number; quantity: number }): void;
}>();

/** 下标即档位 ID：`SegmentedControl` 的泛型不收对象 */
const options = SELL_QUICK_RATIOS.map((r, index) => ({
  label: r.label,
  value: index
}));

const activeIndex = computed(() => {
  const q = props.modelValue;
  // 未填 / 未选持仓时不高亮：此时任何档位「命中」都是假的（0 × 比例 = 0）
  if (q == null || q <= 0 || props.total <= 0) return -1;
  for (let i = 0; i < SELL_QUICK_RATIOS.length; i++) {
    const expected = calcSellQuantityByRatio(
      SELL_QUICK_RATIOS[i].value,
      props.total,
      props.type,
      props.step
    );
    if (Math.abs(q - expected) < 1e-6) return i;
  }
  return -1;
});

function select(index: number) {
  const ratio = SELL_QUICK_RATIOS[index];
  // `total <= 0`（未选持仓 / 持仓已清空）时任何比例都只会算出 0，
  // 静默把它写进输入框会让用户以为「点了没反应」，故直接不响应。
  if (!ratio || props.disabled || props.total <= 0) return;
  const quantity = calcSellQuantityByRatio(
    ratio.value,
    props.total,
    props.type,
    props.step
  );
  emit("update:modelValue", quantity);
  emit("select", { ratio: ratio.value, quantity });
}
</script>

<template>
  <SegmentedControl
    :model-value="activeIndex"
    :options="options"
    :aria-label="ariaLabel"
    :disabled="disabled"
    @change="select"
  />
</template>
