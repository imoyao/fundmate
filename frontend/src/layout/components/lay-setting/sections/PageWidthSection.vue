<!-- 页宽：固定 / 自定义（自定义时给出 1280–1600 的数值输入） -->
<script setup lang="ts">
import { computed } from "vue";
import Segmented, { type OptionsType } from "@/components/ReSegmented";
import {
  SECTION_TITLE_CLASS,
  isStretchNumber,
  stretchIndex,
  stretchValueOf
} from "./settingModel";
import LeftArrow from "~icons/ri/arrow-left-s-line?width=20&height=20";
import RightArrow from "~icons/ri/arrow-right-s-line?width=20&height=20";

const props = defineProps<{
  /**
   * 当前页宽：`false` 表示「固定」，数字表示自定义宽度。
   * 类型里带 `true`：`settings.stretch` 可能来自「点击拉伸按钮」的 `!stretch`，
   * 那一步会写入布尔 `true`（历史行为，`isStretchNumber` 会把它当「固定」处理）。
   */
  stretch: number | boolean;
}>();

const emit = defineEmits<{
  /** 输入框里改数值：只更新展示值，不落存储（与原 `v-model` + `@change` 同构） */
  "update:stretch": [value: number | boolean];
  /** 确认落存储（档位切换 / 输入框 change / 点击拉伸按钮） */
  commit: [value: number | boolean];
}>();

const index = computed(() => stretchIndex(props.stretch));

const stretchTypeOptions = computed<Array<OptionsType>>(() => [
  { label: "固定", tip: "紧凑页面，轻松找到所需信息", value: "fixed" },
  { label: "自定义", tip: "最小1280、最大1600", value: "custom" }
]);

function onTypeChange({ option }: { option: OptionsType }) {
  emit("commit", stretchValueOf(option.value));
}
</script>

<template>
  <div>
    <p :class="['mt-5!', ...SECTION_TITLE_CLASS]">页宽</p>
    <Segmented
      resize
      class="mb-2 select-none"
      :modelValue="index"
      :options="stretchTypeOptions"
      @change="onTypeChange"
    />
    <el-input-number
      v-if="isStretchNumber(props.stretch)"
      :model-value="props.stretch"
      :min="1280"
      :max="1600"
      controls-position="right"
      @update:model-value="v => emit('update:stretch', v)"
      @change="v => emit('commit', v)"
    />
    <button
      v-else
      v-ripple="{ class: 'text-gray-300' }"
      aria-label="切换页宽（拉伸／非拉伸）"
      class="bg-transparent flex-c w-full h-20 rounded-md border border-[var(--pure-border-color)]"
      @click="emit('commit', !props.stretch)"
    >
      <div
        class="flex-bc transition-all duration-300"
        :class="[props.stretch ? 'w-[24%]' : 'w-[50%]']"
        style="color: var(--brand-ink)"
      >
        <IconifyIconOffline :icon="props.stretch ? RightArrow : LeftArrow" />
        <div
          class="grow border-0 border-b border-dashed"
          style="border-color: var(--el-color-primary)"
        />
        <IconifyIconOffline :icon="props.stretch ? LeftArrow : RightArrow" />
      </div>
    </button>
  </div>
</template>
