<!-- src/components/QuickEntry/QuickFab.vue -->
<template>
  <div class="fixed bottom-24 right-8 z-50">
    <el-tooltip content="记一笔" placement="left">
      <button
        class="w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        :style="{ backgroundColor: 'var(--el-color-primary)' }"
        @click="emit('open')"
      >
        <IconifyIconOffline icon="ep:plus" class="text-white text-2xl" />
      </button>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";

const emit = defineEmits<{
  open: [];
}>();
</script>
