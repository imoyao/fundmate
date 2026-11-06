<script setup lang="ts">
import CloudUploadIcon from "@/components/CloudUploadIcon/index.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerId,
  parsing,
  uploadAccept,
  beforeUpload,
  handleUpload,
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
        <CloudUploadIcon class="upload-icon" />
        <p class="upload-text">将文件拖到此处，或</p>
        <el-button
          plain
          size="default"
          class="upload-btn"
          :disabled="!selectedLedgerId"
          @click="handleUploadClick"
        >
          点击上传
        </el-button>
        <p class="upload-hint">
          {{
            isStandardMode
              ? "使用标准模板格式的文件"
              : `直接上传${formatName}导出的文件`
          }}
        </p>
        <p class="upload-format-info">支持 Excel、CSV 格式 ｜ 最大 5MB</p>
        <p class="upload-flow-hint">完成上传后进入预览与修正步骤</p>
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
  min-height: 360px;
  padding: 40px;
  background: var(--bg-card);
  border: 1px solid transparent;
  border-radius: 16px;
  box-shadow: var(--shadow-raised);
  transition:
    border-color 0.25s ease,
    background-color 0.25s ease,
    box-shadow 0.25s ease;
}

.golden-upload:hover {
  border-color: var(--border-default);
}

/* 拖拽高亮走 Element Plus 自带的 `.el-upload-dragger.is-dragover`
   （背景 `--el-color-primary-light-9` = `--brand-100`，`2px dashed --el-color-primary` = `--brand-700`，
   映射见 src/style/theme.scss:157-162），无需本组件再写一条。
   #2904 之前这里有两级规则打在根节点 `.golden-upload` 上，而 Element Plus 把 `.is-dragover`
   挂在子元素 `.el-upload-dragger` 上 ⇒ 从未命中；配套的 `isDragover` ref 也从没被写过。
   两者一并删除，删前后渲染无差异（元素与计算样式逐项比对过）。 */

.upload-icon {
  margin-bottom: 16px;
  font-size: var(--text-hero);
  color: var(--brand-700);
  transition:
    color 0.2s,
    transform 0.2s;
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

.upload-btn.is-loading {
  color: var(--brand-700);
}

.upload-text {
  margin: 0 0 16px;
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--text-primary);
}

.upload-hint {
  margin: 12px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.upload-format-info {
  margin-top: 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.upload-flow-hint {
  margin-top: 10px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.upload-error {
  padding: 12px 16px;
  margin-top: 16px;
  font-size: var(--text-small);
  color: var(--color-danger);
  text-align: center;
  background: var(--color-danger-10);
  border: 1px solid var(--color-danger-30);
  border-radius: var(--radius-sm);
}

.upload-error-detail {
  margin-top: 8px;
  font-size: var(--text-label);
  line-height: 1.6;
  text-align: left;
}
</style>
