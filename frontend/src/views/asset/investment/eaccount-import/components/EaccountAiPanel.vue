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

    <!-- AI 识别方式分段（粘贴文本 / 上传图片）
         #1731 收敛：原手写 `.ocr-segmented`（--brand-600 实底，白字实测 3.02:1 不达 AA）
         已改为 SegmentedControl 的 small 档（软按钮规范）。
         布局钩子改名为 `.ai-tab-switch`：旧名以 `-segmented` 结尾，会被守卫
         `scripts/guard_segmented.py` 判为回潮（见 frontend/design.md「Segmented」编码红线）。 -->
    <SegmentedControl
      v-model="p.aiTab"
      class="ai-tab-switch"
      :options="AI_TAB_OPTIONS"
      size="small"
      aria-label="AI 识别方式"
    />

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
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import type { useEaccountImport } from "../composables/useEaccountImport";

defineOptions({ name: "EaccountAiPanel" });

/** AI 识别方式分段选项（#1731）：`as const` 保留字面量类型，供 SegmentedControl 泛型推断 */
const AI_TAB_OPTIONS = [
  { label: "粘贴文本", value: "text" },
  { label: "上传图片", value: "image" }
] as const;

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

/* 识别方式分段（文本 / 图片）：外观全部由 SegmentedControl `small` 档负责，
   此处**只补与下方输入区 / 上传区的间距**（#1731）。 */
.ai-tab-switch {
  margin-bottom: var(--space-compact);
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
