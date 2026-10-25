<!-- 主题色：色块列表，点击切换 -->
<script setup lang="ts">
import type { themeColorsType } from "@/layout/types";
import {
  SECTION_TITLE_CLASS,
  showThemeColor,
  themeColorMark
} from "./settingModel";
import Check from "~icons/ep/check";

const props = defineProps<{
  colors: themeColorsType[];
  /** 当前生效的主题色（`layoutTheme.theme`） */
  activeTheme: string;
  isDark: boolean;
}>();

const emit = defineEmits<{ select: [themeColor: string] }>();
</script>

<template>
  <div>
    <p :class="['mt-5!', ...SECTION_TITLE_CLASS]">主题色</p>
    <ul class="theme-color">
      <li
        v-for="(item, index) in props.colors"
        v-show="showThemeColor(item.themeColor, props.isDark)"
        :key="index"
        :style="{ background: item.color }"
        role="button"
        tabindex="0"
        @keydown.enter="emit('select', item.themeColor)"
        @click="emit('select', item.themeColor)"
      >
        <el-icon
          style="margin: 0.1em 0.1em 0 0"
          :size="17"
          :color="themeColorMark(item.themeColor, props.activeTheme)"
        >
          <IconifyIconOffline :icon="Check" />
        </el-icon>
      </li>
    </ul>
  </div>
</template>

<style lang="scss" scoped>
/* scoped 说明：色块是本组件内部元素，拿不到父组件的 scopeId，
   `.theme-color` 这套必须自带一份（父层 `:deep()` 只能穿透到子组件根节点） */
.theme-color {
  height: 20px;

  li {
    float: left;
    height: 20px;
    margin-right: 8px;
    cursor: pointer;
    border-radius: 4px;

    &:nth-child(1) {
      border: 1px solid #ddd;
    }
  }
}
</style>
