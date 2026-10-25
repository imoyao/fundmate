<script setup lang="ts">
/**
 * 模块四：底部操作区（#980 拆分）。
 *
 * 转换不走这里：它的提交发生在步骤条第 3 步（确认转换），且第 4 步是结果页——
 * 全局按钮在那里没有可提交的对象，所以整条由父页 `v-if` 隐藏，不在本组件内判断。
 */
defineProps<{ submitting: boolean }>();

const emit = defineEmits<{
  (e: "cancel"): void;
  (e: "submit"): void;
}>();
</script>

<template>
  <div
    class="pt-4 border-t flex justify-end gap-3"
    :style="{ borderColor: 'var(--border-default)' }"
  >
    <el-button class="action-btn" @click="emit('cancel')">取消</el-button>
    <el-button
      class="action-btn"
      type="primary"
      :loading="submitting"
      @click="emit('submit')"
    >
      确认记账
    </el-button>
  </div>
</template>

<style scoped>
.action-btn {
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.15s;
}

.action-btn:active {
  box-shadow: none !important;
  transform: translateY(1px) scale(0.96);
}
</style>
