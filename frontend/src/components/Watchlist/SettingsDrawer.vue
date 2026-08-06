<template>
  <el-drawer
    v-model="visible"
    title="管理自选"
    size="360px"
    direction="rtl"
    destroy-on-close
  >
    <div class="settings-drawer-body space-y-4">
      <!-- 管理分组 -->
      <div
        class="settings-card rounded-xl p-4 cursor-pointer transition-shadow"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
        @click="emit('manage-groups')"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--brand-100)' }"
          >
            <IconifyIconOffline
              icon="ep:folder"
              class="text-lg"
              :style="{ color: 'var(--brand-700)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              管理分组
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              创建、重命名或删除自定义分组
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary)' }"
          />
        </div>
      </div>

      <!-- 管理标签 -->
      <div
        class="settings-card rounded-xl p-4 cursor-pointer transition-shadow"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
        @click="emit('manage-tags')"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          >
            <IconifyIconOffline
              icon="ep:price-tag"
              class="text-lg"
              :style="{ color: 'var(--text-secondary)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              管理标签
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              编辑、新建或删除资产标签
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary)' }"
          />
        </div>
      </div>

      <!-- 批量管理 -->
      <div
        class="settings-card rounded-xl p-4 cursor-pointer transition-shadow"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
        @click="emit('manage-batch')"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--color-warning-20)' }"
          >
            <IconifyIconOffline
              icon="ep:operation"
              class="text-lg"
              :style="{ color: 'var(--color-warning)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              批量管理自选
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              批量移动、删除自选资产
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary)' }"
          />
        </div>
      </div>

      <!-- 导入探市数据 -->
      <div
        v-if="hasPendingExploreData"
        class="settings-card rounded-xl p-4 cursor-pointer transition-shadow"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--brand-400)',
          boxShadow: 'var(--shadow-raised)'
        }"
        @click="handleImportExploreData"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--brand-100)' }"
          >
            <IconifyIconOffline
              icon="ep:download"
              class="text-lg"
              :style="{ color: 'var(--brand-700)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              导入探市数据
              <el-badge :value="'!'" type="danger" class="ml-1" />
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              将「探市」中的观察资产迁移到自选列表
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary)' }"
          />
        </div>
      </div>

      <!-- 排序设置（预留） -->
      <div
        class="settings-card rounded-xl p-4 opacity-50 cursor-not-allowed"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          >
            <IconifyIconOffline
              icon="ep:sort"
              class="text-lg"
              :style="{ color: 'var(--text-disabled)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-disabled)' }"
            >
              排序设置
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-disabled)' }">
              自定义列表排序规则（开发中）
            </p>
          </div>
          <span
            class="px-2 py-0.5 text-[10px] rounded-full"
            :style="{
              backgroundColor: 'var(--bg-soft)',
              color: 'var(--text-tertiary)'
            }"
          >
            即将推出
          </span>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { useSupabaseAuth } from "@/composables/useSupabaseAuth";

const { hasPendingExploreData, manualMigrate } = useSupabaseAuth();

const handleImportExploreData = async () => {
  try {
    const count = await manualMigrate();
    ElMessage.success(`成功导入 ${count} 个资产到「观察仓」`);
  } catch (e: any) {
    ElMessage.error(e.message || "导入失败");
  }
};

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  "manage-groups": [];
  "manage-tags": [];
  "manage-batch": [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});
</script>

<style scoped>
.settings-drawer-body {
  padding: 0 4px;
}

.settings-card {
  transition: all 0.15s ease;
}

.settings-card:hover {
  box-shadow: var(--shadow-float) !important;
}

/* 主按钮动效 */
:deep(.el-button--primary:active) {
  box-shadow: none !important;
  transform: translateY(1px) scale(0.96);
}
</style>
