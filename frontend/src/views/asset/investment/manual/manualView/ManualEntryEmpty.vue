<script setup lang="ts">
/**
 * 模块三的空态：还没选账户（#980 拆分）。
 *
 * 账户是「操作类型」和「表单」两个模块的前置条件，没选时后面两块都无从渲染，
 * 所以这块是空态而不是「禁用态」——按钮灰着但没有解释，用户只会以为是坏了。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
</script>

<template>
  <div
    class="py-12 text-center border-2 border-dashed rounded-xl"
    :style="{ borderColor: 'var(--border-default)' }"
  >
    <IconifyIconOffline
      icon="ep:pointer"
      class="text-4xl mb-3"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    />
    <p class="text-base font-medium" :style="{ color: 'var(--text-primary)' }">
      请先从上方选择交易账户
    </p>
    <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
      我们将根据账户类型自动匹配可用的记账操作
    </p>
  </div>
</template>
