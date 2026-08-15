<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

defineProps<{ row: any }>();

const { startEdit, finishEdit, cancelEdit } = useImportWizardContext();
</script>

<template>
  <el-popover
    :visible="row.isEditingPrice"
    placement="bottom-start"
    :width="200"
    :trigger="'manual' as any"
    :hide-after="0"
    :persistent="true"
    teleported
  >
    <div class="flex flex-col gap-2" @mousedown.stop>
      <div class="text-xs text-gray-500">
        {{ row.symbol }} {{ row.name }} -
        <span class="font-semibold">价格</span>
      </div>
      <!-- eslint-disable vue/no-mutating-props -->
      <el-input-number
        ref="inputRef"
        v-model="row.price"
        size="default"
        :precision="4"
        :min="0"
        class="w-full"
        controls-position="right"
        @vue:mounted="(el: any) => el?.input?.focus()"
      />
      <!-- eslint-enable vue/no-mutating-props -->
      <div class="flex justify-end gap-2">
        <el-button
          type="primary"
          size="small"
          @click.stop="finishEdit(row, 'price', true)"
          >确认</el-button
        >
        <el-button size="small" @click.stop="cancelEdit(row, 'price')"
          >取消</el-button
        >
      </div>
    </div>
    <template #reference>
      <span
        class="cursor-pointer hover:text-blue-500 select-none"
        @click.stop="startEdit(row, 'price')"
        @mousedown.prevent
      >
        {{ row.price }}
        <el-tag
          v-if="row.is_calculated"
          size="small"
          type="warning"
          class="ml-1"
          >待确认</el-tag
        >
      </span>
    </template>
  </el-popover>
</template>
