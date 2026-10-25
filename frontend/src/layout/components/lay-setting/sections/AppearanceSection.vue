<!-- 整体风格：浅色 / 深色 / 自动 -->
<script setup lang="ts">
import { computed } from "vue";
import Segmented, { type OptionsType } from "@/components/ReSegmented";
import {
  SECTION_TITLE_CLASS,
  overallStyleIndex,
  type ThemeStyleOption
} from "./settingModel";
import DayIcon from "@/assets/svg/day.svg?component";
import DarkIcon from "@/assets/svg/dark.svg?component";
import SystemIcon from "@/assets/svg/system.svg?component";

const props = defineProps<{
  /** light / dark / system */
  overallStyle: string;
  /** 当前是否暗色（与 `overallStyle` 是两件事：`system` 档下它由系统主题决定） */
  dataTheme: boolean;
  /** 网页整体是否为暗色风格（决定图标填色） */
  isDark: boolean;
}>();

const emit = defineEmits<{
  change: [payload: { index: number; option: ThemeStyleOption }];
}>();

const index = computed(() =>
  overallStyleIndex(props.overallStyle, props.dataTheme)
);

const themeOptions = computed<Array<ThemeStyleOption>>(() => [
  {
    label: "浅色",
    icon: DayIcon,
    theme: "light",
    tip: "清新启航，点亮舒适的工作界面",
    iconAttrs: { fill: props.isDark ? "#fff" : "#000" }
  },
  {
    label: "深色",
    icon: DarkIcon,
    theme: "dark",
    tip: "月光序曲，沉醉于夜的静谧雅致",
    iconAttrs: { fill: props.isDark ? "#fff" : "#000" }
  },
  {
    label: "自动",
    icon: SystemIcon,
    theme: "system",
    tip: "同步时光，界面随晨昏自然呼应",
    iconAttrs: { fill: props.isDark ? "#fff" : "#000" }
  }
]);

/** Segmented 的 props 只声明 `OptionsType`，`theme` 是我们额外带的字段 */
const options = computed<Array<OptionsType>>(() => themeOptions.value);
</script>

<template>
  <div>
    <p :class="SECTION_TITLE_CLASS">整体风格</p>
    <Segmented
      resize
      class="select-none"
      :modelValue="index"
      :options="options"
      @change="emit('change', $event)"
    />
  </div>
</template>
