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

      <!-- 刷新频率 -->
      <div
        v-if="realtimeEnabled"
        class="settings-card rounded-xl p-4"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--color-success-20)' }"
          >
            <IconifyIconOffline
              icon="ep:timer"
              class="text-lg"
              :style="{ color: 'var(--color-success)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              实时估值刷新频率
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              盘中自动轮询估值的间隔，收盘/休市自动暂停
            </p>
          </div>
          <el-segmented
            :model-value="refreshInterval"
            size="small"
            :options="intervalOptions"
            class="refresh-segmented"
            @change="onRefreshIntervalChange"
          />
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
import {
  REFRESH_INTERVAL_OPTIONS,
  type RefreshInterval
} from "@/composables/useRealtimeQuotes";

const { hasPendingExploreData, manualMigrate } = useSupabaseAuth();

const handleImportExploreData = async () => {
  try {
    const result = await manualMigrate();
    ElMessage.success(
      `成功导入 ${result.imported} 个资产到「观察中」${
        result.skipped > 0 ? `，跳过已存在 ${result.skipped} 个` : ""
      }`
    );
  } catch (e: any) {
    ElMessage.error(e.message || "导入失败");
  }
};

const props = defineProps<{
  modelValue: boolean;
  realtimeEnabled?: boolean;
  refreshInterval?: RefreshInterval;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  "manage-groups": [];
  "manage-tags": [];
  "manage-batch": [];
  "refresh-interval-change": [value: RefreshInterval];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

/** 刷新档位选项（label 与 explore 页一致：`${s}s`） */
const intervalOptions = REFRESH_INTERVAL_OPTIONS.map(s => ({
  label: `${s}s`,
  value: s
}));

/** 切换刷新档位：向上抛给页面（页面负责持久化与重启定时器） */
const onRefreshIntervalChange = (value: string | number | boolean) => {
  emit("refresh-interval-change", value as RefreshInterval);
};
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

/* ======================================
   刷新频率 segmented：与 watchlist 页 refresh-segmented 统一胶囊语言
   （design.md：分段控制器胶囊化，选中态软按钮 --brand-100/--brand-700）
   ====================================== */
.refresh-segmented :deep(.el-segmented) {
  height: 24px;
  padding: 2px;
  background-color: var(--bg-muted);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.refresh-segmented :deep(.el-segmented__item) {
  height: 20px;
  padding: 0 10px;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.refresh-segmented :deep(.el-segmented__item:hover) {
  color: var(--text-primary);
}

.refresh-segmented :deep(.el-segmented__item.is-selected) {
  color: var(--brand-700);
  background-color: var(--brand-100);
  box-shadow: none;
}

.refresh-segmented :deep(.el-segmented__item.is-selected:hover) {
  background-color: var(--brand-200);
}

/* EP 选中态背景是独立子元素（默认白底+阴影），一并覆盖为品牌软按钮色 */
.refresh-segmented :deep(.el-segmented__item-selected) {
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.refresh-segmented
  :deep(.el-segmented__item.is-selected:hover .el-segmented__item-selected) {
  background-color: var(--brand-200);
}
</style>
