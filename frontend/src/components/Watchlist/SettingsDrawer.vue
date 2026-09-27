<template>
  <el-drawer
    v-model="visible"
    title="管理自选"
    size="360px"
    direction="rtl"
    destroy-on-close
  >
    <div class="settings-drawer-body space-y-4">
      <!-- 分组小标题：资产管理（组一：管理分组 / 管理标签 / 批量管理 / 导入探市） -->
      <p
        class="settings-group-title text-xs pt-2"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        资产管理
      </p>

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
            :style="{ backgroundColor: 'var(--bg-soft)' }"
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
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              创建、重命名或删除自定义分组
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary-ink)' }"
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
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              编辑、新建或删除资产标签
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary-ink)' }"
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
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          >
            <IconifyIconOffline
              icon="ep:operation"
              class="text-lg"
              :style="{ color: 'var(--color-warning-ink)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              批量管理自选
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              批量移动、删除自选资产
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary-ink)' }"
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
            :style="{ backgroundColor: 'var(--bg-soft)' }"
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
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              将「探市」中的观察资产迁移到自选列表
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          />
        </div>
      </div>

      <!-- 分组小标题：系统设置（组二：排序设置 / 刷新频率） -->
      <p
        class="settings-group-title text-xs pt-2"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        系统设置
      </p>

      <!-- 列显示设置（#993）：点击打开宽模态框，按品类导航分别控制（方案三，2026-09-12） -->
      <div
        class="settings-card rounded-xl p-4 cursor-pointer transition-shadow"
        :style="{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-light)',
          boxShadow: 'var(--shadow-raised)'
        }"
        @click="columnDialogVisible = true"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          >
            <IconifyIconOffline
              icon="ep:grid"
              class="text-lg"
              :style="{ color: 'var(--brand-700)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              表格列显示
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              按品类分组设置展示列（本机自动保存）
            </p>
          </div>
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="text-sm"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          />
        </div>
      </div>

      <ColumnSettingsModal
        v-model="columnDialogVisible"
        :column-settings="columnSettings"
      />

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
              :style="{ color: 'var(--text-tertiary-ink)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              排序设置
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              自定义列表排序规则（开发中）
            </p>
          </div>
          <span
            class="px-2 py-0.5 text-[10px] rounded-full"
            :style="{
              backgroundColor: 'var(--bg-soft)',
              color: 'var(--text-tertiary-ink)'
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
        <!-- 方案 B：纵向布局——图标+标题+说明在上行，segmented 占整行在下行，
             避免抽屉 360px 下分段控制器与标题挤占右侧热区 -->
        <div class="flex items-center gap-3 mb-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center"
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          >
            <IconifyIconOffline
              icon="ep:timer"
              class="text-lg"
              :style="{ color: 'var(--brand-700)' }"
            />
          </div>
          <div class="flex-1">
            <h4
              class="text-sm font-medium mb-1"
              :style="{ color: 'var(--text-primary)' }"
            >
              实时估值刷新频率
            </h4>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
              轮询间隔时长（休市自动暂停）
            </p>
          </div>
        </div>
        <!-- 刷新频率：SegmentedControl small + block 档（design.md「Segmented」唯一实现，
             见 docs/design/components.md）；block 让 4 档均分铺满抽屉宽度 -->
        <SegmentedControl
          :model-value="refreshInterval ?? DEFAULT_REFRESH_INTERVAL"
          :options="intervalOptions"
          size="small"
          block
          aria-label="实时估值刷新频率"
          @change="onRefreshIntervalChange"
        />
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { useSupabaseAuth } from "@/composables/useSupabaseAuth";
import {
  DEFAULT_REFRESH_INTERVAL,
  REFRESH_INTERVAL_OPTIONS,
  type RefreshInterval
} from "@/composables/useRealtimeQuotes";
import type { WatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";
import ColumnSettingsModal from "@/components/Watchlist/ColumnSettingsModal.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";

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
  /** 列显隐偏好实例（#993）：与自选页共享同一单例，勾选即时反映到表格 */
  columnSettings?: WatchlistColumnVisibility;
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

// ── 列显示设置（#993）：入口卡片打开宽模态框（方案三，2026-09-12）──
const columnDialogVisible = ref(false);

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
  /* 列显示分组后卡片内容变长，确保抽屉内可纵向滚动（不撑破布局） */
  max-height: calc(100vh - 56px);
  padding: 0 4px;
  overflow-y: auto;
}

/* 分组小标题：text-xs + --text-tertiary，贴近本组卡片、与上一组拉开间距
   （space-y-4 提供 16px 组内间距，pt-2 额外 8px 组间距；不加分割线避免视觉噪音） */
.settings-group-title {
  font-weight: 500;
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
