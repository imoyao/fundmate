<script setup lang="ts">
/**
 * TradeSlotSwitch · 交易时点（15:00 前 / 后）开关。
 *
 * ## 为什么要有这个组件（#2339 收编尾单）
 *
 * 「15:00 前 / 后」在仓里曾出现 **5 处各写各的**：`BuyForm` / `SellForm` /
 * `DividendForm` / `TransactionEditDialog` 用 `el-radio-button`（选中态是实底
 * `--brand-solid`，与同屏主按钮撞脸），`ConversionForm` 用 `SegmentedControl`。
 * 同一个交互两种外观，`#2336` 引入的，`#2339` 收编。
 *
 * 收编时又踩到一个**文案漂移**：4 处手抄的标签是 `15:00前`（无空格），
 * `ConversionForm` 是 `15:00 前`（有空格）。同一控件在不同表单里字号、间距、
 * 文案都不一致，所以**选项表必须只有一份**——就放在本组件里，不导出给外部改。
 *
 * ## 为什么对外是 `boolean`，不是 `"before" | "after"`
 *
 * 5 处调用点的真相源都是 `isAfter15: boolean`，被 `watch`、确认日计算
 * （`useFundTradeDate`）、提交参数直接消费。改类型等于波及后端契约。
 * 而 `SegmentedControl` 的泛型是 `T extends string | number`，**刻意不收 boolean**
 * （`true/false` 落到 DOM 上就是两个无名选项）。
 *
 * 所以适配只做在**本组件的边界**：对外收/发 `boolean`，对内换字符串。
 * 调用方从此只写 `<TradeSlotSwitch v-model="form.isAfter15" />`，
 * 不必再各自维护一层 `computed`。
 *
 * ## 档位尺寸
 *
 * 固定 `default`（32px 轨道），不用 `small`：它永远与 32px 的 `el-date-picker`
 * 同排，`small`（24px）会在同一行里矮一截。
 */
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";

defineOptions({ name: "TradeSlotSwitch" });

const props = withDefaults(
  defineProps<{
    /** 是否 15:00 后（布尔真相源，与 `form.isAfter15` 同构） */
    modelValue: boolean;
    /** 读屏标签；同页多组时用于区分（默认「交易时点」） */
    ariaLabel?: string;
    disabled?: boolean;
  }>(),
  { ariaLabel: "交易时点", disabled: false }
);

const emit = defineEmits<{
  (e: "update:modelValue", isAfter15: boolean): void;
}>();

/** 唯一一份选项表：标签带空格（时间与中文之间留白），别在调用处再写一遍 */
const TRADE_SLOT_OPTIONS = [
  { label: "15:00 前", value: "before" },
  { label: "15:00 后", value: "after" }
] as const;

const slot = computed<"before" | "after">({
  get: () => (props.modelValue ? "after" : "before"),
  set: v => emit("update:modelValue", v === "after")
});
</script>

<template>
  <SegmentedControl
    v-model="slot"
    :options="TRADE_SLOT_OPTIONS"
    :aria-label="ariaLabel"
    :disabled="disabled"
  />
</template>
