<script setup lang="ts">
import Superellipse from "@/components/Superellipse/index.vue";
import { ALLOCATION_OPTIONS } from "@/constants";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerId,
  parsing,
  fileSize,
  selectedLedgerName,
  ledgerTypeLabel,
  currentStep,
  isStandardMode,
  downloadLoading,
  handleDownloadTemplate,
  templateNameForAccount,
  accountType,
  templateFields,
  selectedMode,
  availableModes,
  logoBrokenMap,
  onLogoError,
  uploadAccept,
  beforeUpload,
  handleUpload,
  isDragover,
  uploading,
  handleUploadClick,
  formatName,
  uploadError,
  formatGuides,
  showCreateLedgerDialog,
  createLedger,
  newLedgerName,
  newLedgerAllocation,
} = useImportWizardContext();
</script>

<template>
  <div class="upload-step">
    <div v-show="parsing" class="parsing-status">
      <p class="text-sm text-gray-500 mb-4">
        <IconifyIconOffline icon="ep:loading" class="loading-icon" />
        正在解析文件，请稍候...
      </p>
      <p class="text-xs text-gray-400 mb-4">
        正在处理 {{ fileSize }}，预计需要 5-10 秒
      </p>
      <el-skeleton :rows="8" animated />
    </div>

    <div v-show="!parsing" class="upload-layout">
      <div class="upload-left">
        <div class="ledger-select-area">
          <div class="flex items-center gap-4">
            <span class="text-base font-medium text-gray-700">交易账户：</span>
            <el-tag size="large" type="primary"
              >{{ selectedLedgerName }}（{{ ledgerTypeLabel }}）</el-tag
            >
            <el-button type="primary" link @click="currentStep = 0"
              >更换账户</el-button
            >
          </div>
        </div>

        <div v-if="isStandardMode" class="template-download-section">
          <el-button
            type="primary"
            size="large"
            class="download-template-btn"
            :loading="downloadLoading"
            @click="handleDownloadTemplate"
          >
            <IconifyIconOffline icon="ep:download" class="mr-2" />
            下载{{ templateNameForAccount }}（CSV）
          </el-button>
          <p class="download-hint">
            按模板填写后上传，即可批量导入{{ accountType }}交易记录<br />
            模板包含：{{ templateFields }}
          </p>
        </div>

        <div class="import-mode-select">
          <span class="import-mode-label">导入格式：</span>
          <el-select v-model="selectedMode" size="large" style="width: 220px">
            <el-option
              v-for="mode in availableModes"
              :key="mode.value"
              :label="mode.label"
              :value="mode.value"
            />
          </el-select>
          <span class="import-mode-hint">选择与您的文件来源匹配的格式</span>
        </div>

        <div class="source-logos">
          <span class="source-logos-label">支持来源</span>
          <div class="source-logo-pills">
            <button
              v-for="mode in availableModes"
              :key="mode.value"
              type="button"
              class="source-logo-pill"
              :class="{ 'is-active': selectedMode === mode.value }"
              @click="selectedMode = mode.value"
            >
              <Superellipse
                v-if="mode.logo && !logoBrokenMap[mode.value]"
                :power="3"
                class="source-logo-frame"
              >
                <img
                  :src="mode.logo"
                  :alt="mode.label"
                  class="source-logo-img"
                  @error="onLogoError(mode.value)"
                />
              </Superellipse>
              <span v-else class="source-logo-fallback">
                <IconifyIconOffline icon="ep:document" />
              </span>
              <span class="source-logo-name">{{ mode.label }}</span>
            </button>
          </div>
        </div>

        <div class="upload-area-wrapper">
          <el-upload
            ref="uploadRef"
            :accept="uploadAccept"
            :before-upload="beforeUpload"
            :http-request="handleUpload"
            :show-file-list="false"
            drag
            :disabled="!selectedLedgerId || parsing"
            class="golden-upload"
          >
            <template #default>
              <IconifyIconOffline
                icon="ep:upload-filled"
                class="upload-icon"
                :class="{ 'icon-active': isDragover }"
              />
              <p class="upload-text">将文件拖到此处，或</p>
              <el-button
                type="primary"
                size="default"
                class="upload-btn"
                :disabled="!selectedLedgerId || uploading"
                :loading="uploading"
                @click="handleUploadClick"
              >
                {{ uploading ? "正在上传..." : "点击上传" }}
              </el-button>
              <p class="upload-hint">
                {{
                  isStandardMode
                    ? "使用标准模板格式的文件"
                    : `直接上传${formatName}导出的文件`
                }}
              </p>
              <p class="upload-format-info">
                支持 Excel、CSV 格式 ｜ 最大 5MB
              </p>
            </template>
          </el-upload>

          <div v-if="uploadError" class="upload-error">
            <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
            {{ uploadError }}
            <div class="upload-error-detail">
              请检查：
              <template v-if="selectedMode === 'ths'">
                1. 是否为同花顺客户端导出的原始文件<br />
                2. 文件是否完整，没有被修改过<br />
                3. 导出格式是否为"制表符分隔的文本文件"
              </template>
              <template v-else-if="selectedMode === 'tiantian_fund'">
                1. 是否从天天基金网页完整复制了表格数据<br />
                2. 确认日期、基金代码、业务类型、确认金额等关键列是否存在<br />
                3. 文件编码是否为 UTF-8
              </template>
              <template v-else>
                1. 是否为纯CSV格式（不是.xlsx直接改后缀）<br />
                2. 表头是否与下载的模板完全一致<br />
                3. 日期格式是否为 YYYY-MM-DD<br />
                4. 股票代码/基金代码是否正确
              </template>
            </div>
          </div>
        </div>
      </div>

      <div v-if="formatGuides[selectedMode]" class="upload-right">
        <div class="format-guide">
          <div class="format-guide-header">
            <IconifyIconOffline
              icon="ep:info-filled"
              class="format-guide-icon"
            />
            <span>{{ formatGuides[selectedMode].title }}</span>
          </div>
          <ol class="format-guide-list">
            <li
              v-for="(tip, index) in formatGuides[selectedMode].tips"
              :key="index"
            >
              {{ tip }}
            </li>
          </ol>
        </div>
      </div>
    </div>

    <p
      style="
        margin-top: 24px;
        font-size: 13px;
        color: var(--text-tertiary);
        text-align: center;
      "
    >
      上传后将进入预览页面，您可以修正错误后确认导入。如有问题，请参考帮助文档。
    </p>

    <el-dialog
      v-model="showCreateLedgerDialog"
      title="添加新账户"
      width="360px"
      :close-on-click-modal="false"
    >
      <el-form label-position="top">
        <el-form-item label="账户名称" required>
          <el-input
            v-model="newLedgerName"
            placeholder="例如：华泰证券、招商银行储蓄卡"
            size="large"
            @keyup.enter="createLedger"
          />
        </el-form-item>
        <el-form-item label="默认配置目标">
          <el-select v-model="newLedgerAllocation" size="large">
            <el-option
              v-for="opt in ALLOCATION_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-end gap-3">
          <el-button @click="showCreateLedgerDialog = false">取消</el-button>
          <el-button type="primary" @click="createLedger">确认添加</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.el-button--large {
  height: 40px;
}

.upload-step {
  min-height: 380px;
  padding: 0;
}

.upload-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  max-width: 1100px;
  margin: 0 auto;
}

.upload-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.upload-right {
  flex-shrink: 0;
  width: 340px;
  margin-top: 120px;
}

.ledger-select-area {
  margin-bottom: 16px;
}

.ledger-select-area :deep(.el-form-item__content) {
  display: block !important;
}

.template-download-section {
  margin: 0 0 16px;
  text-align: left;
}

.download-template-btn,
.upload-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 0 20px;
  font-size: 14px;
  border-radius: 8px;
}

.download-hint {
  max-width: 700px;
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  text-align: left;
}

.import-mode-select {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0 0 20px;
}

.import-mode-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.import-mode-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.source-logos {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 0 0 20px;
}

.source-logos-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.source-logo-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.source-logo-pill {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 8px 14px;
  font-size: 13px;
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    background-color 0.3s ease,
    border-color 0.3s ease,
    box-shadow 0.3s ease,
    transform 0.3s ease;
}

.source-logo-pill:hover {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-200);
  box-shadow: 0 4px 14px rgb(227 79 56 / 8%);
  transform: translateY(-2px);
}

.source-logo-pill.is-active {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-400);
  box-shadow: 0 0 0 2px rgb(227 79 56 / 12%);
}

.source-logo-frame {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  overflow: hidden;
}

.source-logo-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.source-logo-fallback {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 16px;
  color: var(--text-tertiary);
}

.source-logo-name {
  white-space: nowrap;
}

.upload-area-wrapper {
  flex: 1;
}

.golden-upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 300px;
  padding: 32px;
  background: #f5f7fa;
  border: 2px dashed #888;
  border-radius: 14px;
  transition: all 0.3s;
}

.golden-upload:hover {
  border-color: var(--color-primary);
}

.golden-upload.is-dragover {
  background: var(--color-primary-10) !important;
  border: 2px solid var(--color-primary) !important;
}

.golden-upload.is-dragover .upload-icon {
  color: var(--color-primary);
  transform: scale(1.1);
}

.upload-icon {
  margin-bottom: 16px;
  font-size: 64px;
  color: var(--color-primary);
  transition:
    color 0.2s,
    transform 0.2s;
}

.upload-text {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

.upload-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.upload-format-info {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.upload-btn:hover {
  opacity: 0.9;
}

.upload-btn:active {
  transform: scale(0.98);
}

.upload-error {
  padding: 12px 16px;
  margin-top: 16px;
  font-size: 14px;
  color: var(--color-danger);
  text-align: center;
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
  border-radius: 6px;
}

.upload-error-detail {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  text-align: left;
}

.parsing-status {
  width: 100%;
  max-width: 680px;
  margin: 0 auto;
  text-align: center;
}

.loading-icon {
  margin-right: 4px;
  font-size: 16px;
  animation: spin 1s linear infinite;
}

.format-guide {
  padding: 16px;
  margin-top: 0;
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  box-shadow: 0 1px 4px rgb(0 0 0 / 4%);
}

.format-guide-header {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.format-guide-icon {
  font-size: 18px;
  color: var(--color-primary);
}

.format-guide-list {
  padding-left: 0;
  margin: 0;
  list-style: none;
  counter-reset: step-counter;
}

.format-guide-list li {
  display: flex;
  align-items: baseline;
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  counter-increment: step-counter;
}

.format-guide-list li::before {
  flex-shrink: 0;
  min-width: 18px;
  margin-right: 8px;
  font-weight: 600;
  color: var(--color-primary);
  content: counter(step-counter) ".";
}
</style>
