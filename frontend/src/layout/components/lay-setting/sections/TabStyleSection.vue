<!-- 页签风格：灵动 / 卡片 / 谷歌 -->
<script setup lang="ts">
import { computed } from "vue";
import Segmented, { type OptionsType } from "@/components/ReSegmented";
import { SECTION_TITLE_CLASS, markIndex } from "./settingModel";

const props = defineProps<{
  /** smart / card / chrome */
  markValue: string;
}>();

const emit = defineEmits<{ change: [option: OptionsType] }>();

const index = computed(() => markIndex(props.markValue));

const markOptions = computed<Array<OptionsType>>(() => [
  { label: "灵动", tip: "灵动标签，添趣生辉", value: "smart" },
  { label: "卡片", tip: "卡片标签，高效浏览", value: "card" },
  { label: "谷歌", tip: "谷歌风格，经典美观", value: "chrome" }
]);
</script>

<template>
  <div>
    <p :class="['mt-4!', ...SECTION_TITLE_CLASS]">页签风格</p>
    <Segmented
      resize
      class="select-none"
      :modelValue="index"
      :options="markOptions"
      @change="({ option }) => emit('change', option)"
    />
  </div>
</template>
