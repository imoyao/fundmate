<template>
  <!-- AI 识别模式：文本 / 图片 → holding_import → 持仓预览行（独立持仓管线，不建流水） -->
  <div class="ai-import-panel">
    <div class="ai-import-panel__usage">
      <IconifyIconOffline
        icon="ep:magic-stick"
        class="ai-import-panel__usage-icon"
      />
      <span>今日 AI 持仓识别额度剩余</span>
      <strong class="ai-import-panel__usage-count">{{ p.aiRemaining }}</strong>
      / {{ p.aiQuota }} 次
    </div>

    <div class="ocr-segmented" role="tablist" aria-label="AI 识别方式">
      <button
        type="button"
        role="tab"
        class="ocr-segmented__item"
        :class="{ 'is-active': p.aiTab === 'text' }"
        @click="p.aiTab = 'text'"
      >
        粘贴文本
      </button>
      <button
        type="button"
        role="tab"
        class="ocr-segmented__item"
        :class="{ 'is-active': p.aiTab === 'image' }"
        @click="p.aiTab = 'image'"
      >
        上传图片
      </button>
    </div>

    <div v-if="p.aiTab === 'text'" class="ai-import-panel__text">
      <div class="ai-format-hint">
        <p class="ai-format-hint__line">
          粘贴持仓截图里的文字，每行一只，含代码/名称/份额/市值等
        </p>
        <p class="ai-format-hint__example">
          示例：110011 易方达中小盘 份额4526.51 市值5000
        </p>
      </div>
      <el-input
        v-model="p.aiText"
        type="textarea"
        :rows="6"
        resize="vertical"
        placeholder="在此粘贴持仓文本"
      />
    </div>
    <div v-else class="ai-import-panel__image">
      <ImageUploader
        v-model="p.aiImageFile"
        tip="支持券商 / 基金 App 持仓截图，文件不超过 5MB"
      />
    </div>

    <el-button
      type="primary"
      class="ai-import-panel__submit"
      :loading="p.aiRecognizing"
      :disabled="!p.canAiRecognize || p.aiRemaining <= 0"
      @click="p.handleAiRecognize"
    >
      {{ p.aiRecognizing ? "识别中…" : "开始识别" }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import ImageUploader from "@/components/ImageUploader/index.vue";
import type { useEaccountImport } from "../composables/useEaccountImport";

defineOptions({ name: "EaccountAiPanel" });

const props = defineProps<{ page: ReturnType<typeof useEaccountImport> }>();

/**
 * 共享状态单体（useEaccountImport）的响应式视图：
 * reactive 会解包嵌套 ref，模板内可直接读值、v-model 写回同一实例（#980 P1-A 同款）。
 * 外层显隐（!parsedOk && importMode === 'ai'）由 index.vue 编排，与拆分前一致。
 */
const p = reactive(props.page);
</script>

<style scoped>
/* ===== AI 识别面板 ===== */
.ai-import-panel {
  padding: var(--space-standard);
  margin-bottom: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.ai-import-panel__usage {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-standard);
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.ai-import-panel__usage-icon {
  color: var(--brand-600);
}

.ai-import-panel__usage-count {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 识别方式分段（文本 / 图片），与上面 import-mode-switch 同构但更小 */
.ocr-segmented {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  margin-bottom: var(--space-compact);
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.ocr-segmented__item {
  padding: 4px 14px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  transition: all 0.15s ease;
}

.ocr-segmented__item.is-active {
  color: var(--text-inverse);
  background: var(--brand-600);
}

.ai-format-hint {
  margin-bottom: var(--space-2);
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.ai-format-hint__example {
  margin-top: 2px;
  color: var(--text-secondary);
}

.ai-import-panel__submit {
  display: block;
  width: 100%;
  margin-top: var(--space-standard);
}
</style>
