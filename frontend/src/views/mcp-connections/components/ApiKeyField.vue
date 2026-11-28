<!--
  API Key 输入块（自 ServiceCard 拆出，#3304）：粘贴 → 保存 / 取消两态。
  不回显、不落 localStorage——保存即清空，交给父层递交后端加密入库。
-->
<template>
  <div class="mcp-key">
    <el-input
      v-model="apiKey"
      type="password"
      show-password
      clearable
      autocomplete="off"
      placeholder="粘贴 API Key"
      @keyup.enter="onSave"
    />
    <div class="mcp-key__actions">
      <el-button type="primary" :loading="pending" @click="onSave"
        >保存</el-button
      >
      <el-button :disabled="pending" @click="onCancel">取消</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";

defineOptions({ name: "McpApiKeyField" });

defineProps<{
  pending: boolean;
}>();

const emit = defineEmits<{
  save: [apiKey: string];
  cancel: [];
}>();

const apiKey = ref("");

function onSave(): void {
  const key = apiKey.value.trim();
  if (!key) return;
  emit("save", key);
  apiKey.value = "";
}

function onCancel(): void {
  apiKey.value = "";
  emit("cancel");
}
</script>

<style scoped>
.mcp-key {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mcp-key__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
</style>
