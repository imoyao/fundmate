<!-- src/components/QuickEntry/QuickFab.vue -->
<template>
  <div class="fixed bottom-24 right-8 z-50 global-fab">
    <el-tooltip content="记一笔" placement="left">
      <!-- 毛玻璃浮窗样式见 design.md「Elevation & Depth · 毛玻璃」，token 改动须双端同步 -->
      <button
        class="quick-entry-glass w-12 h-12 rounded-full flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        @click="emit('open')"
      >
        <IconifyIconOffline
          icon="ep:plus"
          class="text-2xl"
          :style="{ color: 'var(--brand-700)' }"
        />
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
