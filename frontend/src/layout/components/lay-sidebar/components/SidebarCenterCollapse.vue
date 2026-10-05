<script setup lang="ts">
import { computed } from "vue";
import { useGlobal } from "@pureadmin/utils";
import { useNav } from "@/layout/hooks/useNav";

import ArrowLeft from "~icons/ri/arrow-left-double-fill";

interface Props {
  isActive?: boolean;
}

withDefaults(defineProps<Props>(), {
  isActive: false
});

const { tooltipEffect } = useNav();

const iconClass = computed(() => {
  return ["w-[16px]", "h-[16px]"];
});

const { $storage } = useGlobal<GlobalPropertiesApi>();
const themeColor = computed(() => $storage.layout?.themeColor);

const emit = defineEmits<{
  (e: "toggleClick"): void;
}>();

const toggleClick = () => {
  emit("toggleClick");
};
</script>

<template>
  <!-- 侧栏折叠（#1842 规则二 A 类）：div @click → 真 button。
       折叠是高频操作，键盘此前完全够不到；aria-label 与 tippy 文案同源，
       避免「 tooltip 说点击、屏幕阅读器念别的」这种两套说辞。 -->
  <button
    v-tippy="{
      content: isActive ? '点击折叠' : '点击展开',
      theme: tooltipEffect,
      hideOnClick: 'toggle',
      placement: 'right'
    }"
    type="button"
    class="icon-plain-btn center-collapse"
    :aria-label="isActive ? '折叠侧栏' : '展开侧栏'"
    @click="toggleClick"
  >
    <IconifyIconOffline
      :icon="ArrowLeft"
      :class="[iconClass, themeColor === 'light' ? '' : 'text-primary']"
      :style="{ transform: isActive ? 'none' : 'rotateY(180deg)' }"
    />
  </button>
</template>

<style lang="scss" scoped>
.center-collapse {
  position: absolute;
  top: 50%;
  right: 2px;
  z-index: 1002;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 34px;
  cursor: pointer;
  background: var(--el-bg-color);
  border: 1px solid var(--pure-border-color);
  border-radius: 4px;
  transform: translate(12px, -50%);
}
</style>
