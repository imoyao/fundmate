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
    <div
      class="search-container w-[40px] h-[48px] flex-c cursor-pointer navbar-bg-hover"
      role="button"
      tabindex="0"
      aria-label="打开搜索"
      @keydown.enter="handleSearch"
      @click="handleSearch"
    >
      <IconifyIconOffline icon="ri/search-line" />
    </div>
    <SearchModal v-model:value="show" />
  </div>
</template>
