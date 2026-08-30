<template>
  <!-- 第二步：迁移确认决议面板（§7）：三区呈现 + conflict 行内联决议，全部决议完成后才可提交 -->
  <el-dialog
    v-model="visibleProxy"
    title="确认迁移"
    width="720px"
    destroy-on-close
  >
    <div class="mig-summary">
      <div class="mig-route">
        <span class="mig-route__name">{{ accountName }}</span>
        <IconifyIconOffline icon="ep:arrow-right" class="mig-route__arrow" />
        <span class="mig-route__name">{{ targetLedgerName }}</span>
        <span class="mig-route__total">共 {{ previewItems.length }} 项</span>
      </div>
      <p class="mig-note">
        关闭弹窗不会写入任何数据；确认后按下方决议执行迁移。
      </p>
    </div>

    <div class="mig-body">
      <!-- 区一：直接迁移 -->
      <section v-if="keepItems.length" class="mig-section">
        <header class="mig-section__head">
          <span class="mig-section__title">直接迁移</span>
          <span class="mig-section__count">{{ keepItems.length }} 项</span>
          <span class="mig-section__hint">来源数值原样并入目标账户</span>
        </header>
        <ul class="mig-rows">
          <li
            v-for="item in keepItems"
            :key="migrationRowKey(item)"
            class="mig-row"
          >
            <span class="mig-row__name">
              {{ item.name }}
              <span v-if="item.symbol" class="mig-row__symbol">{{
                item.symbol
              }}</span>
            </span>
            <span class="mig-row__values">{{ snapshotSummary(item) }}</span>
          </li>
        </ul>
      </section>

      <!-- 区二：重复自动丢弃 -->
      <section v-if="duplicateItems.length" class="mig-section">
        <header class="mig-section__head">
          <span class="mig-section__title">重复自动丢弃</span>
          <span class="mig-section__count">{{ duplicateItems.length }} 项</span>
          <span class="mig-section__hint"
            >与目标账户数据一致，只保留一份、不相加</span
          >
        </header>
        <ul class="mig-rows">
          <li
            v-for="item in duplicateItems"
            :key="migrationRowKey(item)"
            class="mig-row"
          >
            <span class="mig-row__name">
              {{ item.name }}
              <span v-if="item.symbol" class="mig-row__symbol">{{
                item.symbol
              }}</span>
            </span>
            <span class="mig-row__values">{{ snapshotSummary(item) }}</span>
          </li>
        </ul>
      </section>

      <!-- 区三：需要你决议（conflict 行内联单选） -->
      <section v-if="conflictItems.length" class="mig-section">
        <header class="mig-section__head">
          <span class="mig-section__title">需要你决议</span>
          <span class="mig-section__count">{{ conflictItems.length }} 项</span>
          <span class="mig-section__hint"
            >同一标的两边数值不一致，逐条选择处理方式</span
          >
        </header>

        <MigrationConflictCard
          v-for="item in conflictItems"
          :key="migrationRowKey(item)"
          :item="item"
          :resolution="resolutions[migrationRowKey(item)]"
          @update:resolution="
            val => updateResolution(migrationRowKey(item), val)
          "
        />
      </section>

      <div v-if="!previewItems.length" class="mig-empty">
        两个账户之间没有需要迁移的数据。
      </div>
    </div>

    <template #footer>
      <div class="mig-footer">
        <span class="mig-footer__status">{{ footerStatusText }}</span>
        <div>
          <el-button @click="$emit('cancel')">取消</el-button>
          <el-button
            type="primary"
            :disabled="!previewItems.length || pendingCount > 0"
            :loading="loading"
            @click="$emit('commit')"
            >确认迁移</el-button
          >
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import type {
  MigrationPreviewResult,
  MigrationAction,
  MigrationPreviewItem
} from "@/api/ledger";
import {
  migrationRowKey,
  snapshotSummary
} from "@/composables/useBatchMigration";
import MigrationConflictCard from "./MigrationConflictCard.vue";

const props = defineProps<{
  visible: boolean;
  preview: MigrationPreviewResult | null;
  resolutions: Record<string, MigrationAction>;
  accountName: string;
  targetLedgerName: string;
  pendingCount: number;
  footerStatusText: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  "update:resolutions": [value: Record<string, MigrationAction>];
  commit: [];
  cancel: [];
}>();

const visibleProxy = computed({
  get: () => props.visible,
  set: (v: boolean) => emit("update:visible", v)
});

const previewItems = computed<MigrationPreviewItem[]>(
  () => props.preview?.items ?? []
);
const keepItems = computed(() =>
  previewItems.value.filter(i => i.classification === "keep")
);
const duplicateItems = computed(() =>
  previewItems.value.filter(i => i.classification === "duplicate")
);
const conflictItems = computed(() =>
  previewItems.value.filter(i => i.classification === "conflict")
);

/** 决议变更：以新对象上抛，避免直接变更 resolutions prop（父组件 v-model 回写 ref） */
function updateResolution(key: string, value: MigrationAction) {
  emit("update:resolutions", { ...props.resolutions, [key]: value });
}
</script>

<style scoped>
/* ===== 批量迁移决议面板（§7）：三区呈现 + conflict 行内联决议 ===== */

/* 概要：来源 → 目标 路由与总数 */
.mig-summary {
  margin-bottom: var(--space-3);
}

.mig-route {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.mig-route__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-route__arrow {
  font-size: 14px;
  color: var(--text-tertiary);
}

/* 总数右对齐：等宽数字保证跳动时不抖 */
.mig-route__total {
  margin-left: auto;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.mig-note {
  margin-top: var(--space-1);
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 长列表限高滚动：底栏（状态 + 确认按钮）始终可见 */
.mig-body {
  max-height: 56vh;
  padding-right: 2px;
  overflow-y: auto;
}

.mig-section {
  margin-bottom: var(--space-3);
}

.mig-section__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}

.mig-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-section__count {
  padding: 0 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.mig-section__hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* keep / duplicate 行：名称居左、数值摘要居右 */
.mig-rows {
  padding: 0;
  margin: var(--space-2) 0 0;
  list-style: none;
}

.mig-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.mig-row + .mig-row {
  border-top: 1px dashed var(--border-light);
}

.mig-row__name {
  font-size: 13px;
  color: var(--text-primary);
}

.mig-row__symbol {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: normal;
  color: var(--text-tertiary);
}

.mig-row__values {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  text-align: right;
}

.mig-empty {
  padding: var(--space-loose) 0;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

/* 底栏：左侧状态文案 + 右侧操作按钮 */
.mig-footer {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.mig-footer__status {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
