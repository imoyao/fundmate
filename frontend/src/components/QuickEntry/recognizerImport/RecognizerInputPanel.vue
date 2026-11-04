<script setup lang="ts">
import { nextTick, ref } from "vue";
import { ElInput } from "element-plus";
import ImageUploader from "@/components/ImageUploader/index.vue";
import type { ImportTab } from "./recognizerImportModel";

defineProps<{
  scenario: "txn_import" | "holding_import";
  activeTab: ImportTab;
}>();

/** 三个 model 双向：父层 resetPreview() 依赖「赋值即回写」才能一次清干净 */
const imageFile = defineModel<File | null>("imageFile", { required: true });
const textContent = defineModel<string>("textContent", { required: true });
const textError = defineModel<string>("textError", { required: true });

const textareaRef = ref<InstanceType<typeof ElInput>>();

/** 切到文本通道 / 弹窗打开时由父层调用；文本域此时可能刚挂载，故推到 nextTick */
function focus() {
  void nextTick(() => textareaRef.value?.focus());
}

defineExpose({ focus });
</script>

<template>
  <div v-if="activeTab === 'image'" class="ocr-tab-panel">
    <ImageUploader
      v-model="imageFile"
      :tip="
        scenario === 'txn_import'
          ? '支持券商/基金 App 交易截图，文件不超过 5MB'
          : '支持持仓截图，文件不超过 5MB'
      "
    />
  </div>

  <div v-else class="ocr-tab-panel">
    <el-input
      ref="textareaRef"
      v-model="textContent"
      type="textarea"
      :rows="8"
      resize="vertical"
      class="ocr-textarea"
      :placeholder="
        scenario === 'txn_import'
          ? '在此粘贴交易记录，每行一只，如：110011 易方达中小盘 买入 10000'
          : '在此粘贴持仓，每行一只，如：110011 易方达中小盘 1000 2.5'
      "
      @input="textError = ''"
    />
    <p v-if="textError" class="ocr-textarea__error">{{ textError }}</p>
  </div>
</template>

<style scoped lang="scss">
.ocr-tab-panel {
  min-height: 160px;
}

/* 文本域走 #1772 输入基线令牌：等宽字体直接写在容器上（EP 内部
   `font-family: inherit` 会继承下来），圆角 / 静态描边 / 过渡 / 焦点光晕
   全部由令牌表达，不再 :deep。焦点用 brand-40% 柔光而非全局 --focus-ring，
   与 OcrImportModal 保持同一套「轻聚焦」观感（见 design.md 输入框基线契约）。 */
.ocr-textarea {
  --input-focus-shadow:
    0 0 0 1px var(--brand-700) inset,
    0 0 0 3px color-mix(in srgb, var(--brand-400) 40%, transparent);
  --input-transition: box-shadow 0.2s ease;

  font-family: var(--font-mono);
}

.ocr-textarea__error {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  color: var(--color-danger);
}
</style>
