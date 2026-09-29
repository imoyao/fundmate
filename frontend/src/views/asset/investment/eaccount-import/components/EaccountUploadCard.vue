<template>
  <!-- 大上传卡片：解析成功后由 previewRows/parsedOk 收起让位预览表格 -->
  <div v-if="!p.parsedOk && p.importMode === 'file'" class="upload-collapse">
    <div class="upload-collapse__inner">
      <div class="upload-card">
        <el-upload
          accept=".csv,.xls,.xlsx"
          :before-upload="p.beforeUpload"
          :http-request="p.handleUpload"
          :show-file-list="false"
          drag
          :disabled="p.parsing"
          class="eaccount-upload"
        >
          <template #default>
            <IconifyIconOffline
              icon="lucide:cloud-upload"
              class="upload-icon"
            />
            <p class="upload-text">将文件拖到此处，或</p>
            <el-button plain class="upload-btn" :loading="p.parsing">
              {{ p.parsing ? "正在解析..." : "点击上传" }}
            </el-button>
            <p class="upload-hint">E账户导出文件（基金持仓快照）</p>
            <p class="upload-format-info">支持 Excel、CSV 格式 ｜ 最大 5MB</p>
          </template>
        </el-upload>

        <div v-if="p.uploadError" class="upload-error">
          <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
          {{ p.uploadError }}
          <div class="upload-error-detail">
            请检查：1. 是否为 E账户（中国结算）导出的原始文件；2. 文件是否完整，
            没有被修改过；3. 文件编码是否为 UTF-8
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 解析完成状态条：折叠后的一行反馈 + 重新上传 -->
  <transition name="done-bar">
    <div v-if="p.parsedOk" class="parse-done-bar">
      <IconifyIconOffline
        icon="ep:success-filled"
        class="parse-done-bar__icon"
      />
      <span class="parse-done-bar__file" :title="p.fileName">
        {{ p.fileName }}
      </span>
      <span class="parse-done-bar__summary">
        已解析
        <b class="parse-done-bar__count">{{ p.parseMeta.total }}</b>
        条记录<template v-if="p.errorCount > 0"
          >，其中 {{ p.errorCount }} 条解析失败</template
        >
      </span>
      <el-button text class="parse-done-bar__reset" @click="p.resetUpload">
        <IconifyIconOffline icon="ep:refresh-left" class="mr-1" />
        重新上传
      </el-button>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { useEaccountImport } from "../composables/useEaccountImport";

defineOptions({ name: "EaccountUploadCard" });

const props = defineProps<{ page: ReturnType<typeof useEaccountImport> }>();

/**
 * 共享状态单体（useEaccountImport）的响应式视图（#980 P1-A 同款）。
 * 两块显隐条件与拆分前逐字一致：上传卡片 `!parsedOk && importMode === 'file'`、
 * 完成状态条 `parsedOk`，均留在本组件内，由 index.vue 的步骤一容器统一约束 currentStep。
 */
const p = reactive(props.page);
</script>

<style scoped>
/* ===== 上传区（复用交易导入 UploadArea 的 golden-upload 语言） ===== */
.upload-card {
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.eaccount-upload :deep(.el-upload-dragger) {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 280px;
  padding: 40px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transition:
    border-color 0.25s ease,
    background-color 0.25s ease;
}

.eaccount-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--brand-400);
}

.eaccount-upload :deep(.el-upload-dragger.is-dragover) {
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.upload-icon {
  margin-bottom: 16px;
  font-size: 56px;
  color: var(--brand-700);
}

.upload-text {
  margin: 0 0 16px;
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-primary);
}

.upload-btn {
  height: 40px;
  padding: 0 24px;
  font-size: var(--text-small);
  color: var(--brand-700);
  background: transparent;
  border: 1px solid var(--brand-400);
  border-radius: var(--radius-sm);
  transition:
    background-color 150ms ease,
    border-color 150ms ease;
}

.upload-btn:hover:not(:disabled) {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-600);
}

.upload-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.upload-format-info {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.upload-error {
  padding: 12px 16px;
  margin-top: var(--space-compact);
  font-size: var(--text-small);
  color: var(--color-danger);
  text-align: center;
  background: var(--color-danger-20);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
}

.upload-error-detail {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  text-align: left;
}

/* ===== 上传卡片折叠（解析成功后让位给预览表格） ===== */

/* 外层 grid 行高 1fr→0fr 平滑收缩 + 淡出；el-upload 始终留在 DOM，仅视觉折叠 */
.upload-collapse {
  display: grid;
  grid-template-rows: 1fr;
  transition:
    grid-template-rows 0.35s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.3s ease;
}

.upload-collapse.is-folded {
  grid-template-rows: 0fr;
  opacity: 0;
}

.upload-collapse__inner {
  min-height: 0;
  overflow: hidden;
}

/* ===== 解析完成状态条 ===== */
.parse-done-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  align-items: center;
  padding: var(--space-3) var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.parse-done-bar__icon {
  flex-shrink: 0;
  font-size: 18px;
  color: var(--color-success-ink);
}

.parse-done-bar__file {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.parse-done-bar__summary {
  font-size: var(--text-small);
  color: var(--text-secondary);
  white-space: nowrap;
}

.parse-done-bar__count {
  font-weight: 600;
  color: var(--color-success-ink);
}

.parse-done-bar__reset {
  flex-shrink: 0;
  margin-left: auto;
  color: var(--text-secondary);
}

/* 状态条出现：淡入 + 轻微下落（与折叠收缩同步） */
.done-bar-enter-active {
  transition:
    opacity 0.3s ease,
    transform 0.3s ease;
}

.done-bar-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}

.done-bar-leave-active {
  transition: opacity 0.2s ease;
}

.done-bar-leave-to {
  opacity: 0;
}
</style>
