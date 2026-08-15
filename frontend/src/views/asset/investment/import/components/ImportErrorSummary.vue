<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

withDefaults(
  defineProps<{
    title?: string;
  }>(),
  {
    title: ""
  }
);

const { importErrors, errorSummary } = useImportWizardContext();
</script>

<template>
  <div v-if="importErrors.length > 0" class="mt-4">
    <el-alert
      :title="
        title || `导入过程中 ${importErrors.length} 条记录因以下原因被跳过`
      "
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <div
          v-for="group in errorSummary"
          :key="group.reason"
          class="error-group"
        >
          <p class="error-reason">
            {{ group.reason }}（共 {{ group.count }} 条）
          </p>
          <el-collapse v-if="group.items.length > 1" class="error-collapse">
            <el-collapse-item
              :title="`涉及标的：${group.items.slice(0, 3).join('、')}${group.items.length > 3 ? ' 等' : ''}`"
            >
              <ul class="list-disc pl-4 text-xs">
                <li v-for="item in group.items" :key="item">
                  {{ item }}
                </li>
              </ul>
            </el-collapse-item>
          </el-collapse>
          <p v-else class="text-xs ml-4">{{ group.items[0] }}</p>
        </div>
      </template>
    </el-alert>
  </div>
</template>
