<script setup lang="ts">
import MenuFold from "~icons/ri/menu-fold-fill";
import MenuUnfold from "~icons/ri/menu-unfold-fill";

interface Props {
  isActive?: boolean;
}

withDefaults(defineProps<Props>(), {
  isActive: false
});

const emit = defineEmits<{
  (e: "toggleClick"): void;
}>();

const toggleClick = () => {
  emit("toggleClick");
};
</script>

<template>
  <!-- 顶栏折叠（#1842 规则二 A 类）：div @click → 真 button，同 SidebarCenterCollapse -->
  <button
    type="button"
    class="icon-plain-btn px-3 mr-1 navbar-bg-hover"
    :title="isActive ? '点击折叠' : '点击展开'"
    :aria-label="isActive ? '折叠侧栏' : '展开侧栏'"
    @click="toggleClick"
  >
    <IconifyIconOffline
      :icon="isActive ? MenuFold : MenuUnfold"
      class="inline-block! align-middle hover:text-primary dark:hover:text-white!"
    />
  </button>
</template>
