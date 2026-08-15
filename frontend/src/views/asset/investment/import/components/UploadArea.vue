<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerId,
  parsing,
  uploadAccept,
  beforeUpload,
  handleUpload,
  isDragover,
  uploading,
  handleUploadClick,
  isStandardMode,
  formatName,
  uploadError,
  selectedMode
} = useImportWizardContext();
</script>

<template>
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
        <p class="upload-format-info">支持 Excel、CSV 格式 ｜ 最大 5MB</p>
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
</template>

<style scoped>
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
</style>
