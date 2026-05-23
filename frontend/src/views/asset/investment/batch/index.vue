<template>
  <div class="placeholder-page p-8 text-center">
    <IconifyIconOffline icon="ep:clock" class="text-5xl text-gray-400 mb-4" />
    <h2 class="text-xl font-bold text-gray-700 mb-2">功能开发中</h2>
    <p class="text-gray-500 mb-6">此功能将在后续版本中开放，敬请期待</p>
    <el-button @click="$router.push('/inventory')">返回盘点首页</el-button>
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
</script>
