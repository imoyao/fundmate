<script setup lang="ts">
import { useBoolean } from "../../hooks/useBoolean";
import SearchModal from "./components/SearchModal.vue";

const { bool: show, toggle } = useBoolean();
function handleSearch() {
  toggle();
}
</script>

<template>
  <div>
    <!-- 搜索入口（#1842 规则二 A 类）：div @click → 真 button。
         搜索面板内部已由 onKeyStroke(↑/↓/Enter) 驱动（见 SearchModal），
         但**打开面板这个入口**此前键盘完全够不到。 -->
    <button
      type="button"
      class="icon-plain-btn search-container w-[40px] h-[48px] flex-c cursor-pointer navbar-bg-hover"
      aria-label="搜索"
      @click="handleSearch"
    >
      <IconifyIconOffline icon="ri/search-line" />
    </button>
    <SearchModal v-model:value="show" />
  </div>
</template>
