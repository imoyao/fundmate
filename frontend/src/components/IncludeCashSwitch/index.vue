<script setup lang="ts">
/**
 * IncludeCashSwitch · XIRR 现金流口径（含现金 / 剔除现金）。
 *
 * ## 为什么要有这个组件（#2339 B 组）
 *
 * 「XIRR 是否含现金」这一个业务口径，此前在三个页面各写了一遍 `el-radio-button`
 * （`IntelligentAnalysis` / `portfolio/detail` / `WelcomeXirrTemperature`），
 * 选中态是实底 `--brand-solid`，与同屏主按钮撞脸；而同一仓里「交易时点」
 * 已经收编成 `TradeSlotSwitch`，于是**同一个交互又出现两种外观**。
 *
 * 顺手核过三处的文案与默认值：`剔除现金` 在前、`含现金` 在后，默认都是 `false`
 * —— 没有隐藏的口径分歧，所以可以纯机械收编，不需要动业务语义。
 *
 * ## 为什么对外是 `boolean`
 *
 * 三处调用点的真相源都是 `includeCashEquivalents: boolean`（`ref(false)` 或父组件
 * 传入的 prop），被 `watch`、请求参数与父组件的 `change` 事件消费。
 * 而 `SegmentedControl` 的泛型 `T extends string | number` **刻意不收 boolean**
 * （`true/false` 落到 DOM 上就是两个无名选项）。
 *
 * 所以适配只做在本组件边界：对外收/发 `boolean`，对内换 `exclude | include`。
 *
 * ## 关于 `change`
 *
 * 三处都靠 `@change` 触发重新取数（`loadXirr` / `fetchXirr` / 父级 `change`），
 * 因此本组件在值**真的变化**时额外发一次 `change`。重复点同一项不会发——
 * `SegmentedControl.select()` 自己做了等值短路，`set` 不会被调用。
 */
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";

defineOptions({ name: "IncludeCashSwitch" });

const props = withDefaults(
  defineProps<{
    /** 是否含现金（布尔真相源，与 `includeCashEquivalents` 同构） */
    modelValue: boolean;
    /** 读屏标签；同页多组时用于区分 */
    ariaLabel?: string;
    /** `small` 是三处调用点的实际档位（都在 SectionHeader `#action` 里与 28px 小控件同排） */
    size?: "default" | "small";
    disabled?: boolean;
  }>(),
  { ariaLabel: "现金流口径", size: "small", disabled: false }
);

const emit = defineEmits<{
  (e: "update:modelValue", includeCash: boolean): void;
  (e: "change", includeCash: boolean): void;
}>();

/** 唯一一份选项表：与三处原文案逐字一致，别在调用处再写一遍 */
const INCLUDE_CASH_OPTIONS = [
  { label: "剔除现金", value: "exclude" },
  { label: "含现金", value: "include" }
] as const;

const include = computed<"exclude" | "include">({
  get: () => (props.modelValue ? "include" : "exclude"),
  set: v => {
    const next = v === "include";
    emit("update:modelValue", next);
    emit("change", next);
  }
});
</script>

<template>
  <SegmentedControl
    v-model="include"
    :options="INCLUDE_CASH_OPTIONS"
    :size="size"
    :aria-label="ariaLabel"
    :disabled="disabled"
  />
</template>
