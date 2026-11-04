<script setup lang="ts">
import ParsingStatus from "./ParsingStatus.vue";
import TemplateDownloadSection from "./TemplateDownloadSection.vue";
import ModeSelect from "./ModeSelect.vue";
import UploadArea from "./UploadArea.vue";
import FormatGuide from "./FormatGuide.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const {
  selectedLedgerName,
  ledgerTypeLabel,
  currentStep,
  formatGuides,
  selectedMode,
  parsing
} = useImportWizardContext();
</script>

<template>
  <div class="upload-step">
    <ParsingStatus v-show="parsing" />

    <div v-show="!parsing" class="upload-layout">
      <div class="upload-left">
        <div class="ledger-select-area">
          <div class="flex items-center gap-4">
            <span class="text-base font-medium text-[var(--text-primary)]"
              >交易账户：</span
            >
            <el-tag size="large" type="primary"
              >{{ selectedLedgerName }}（{{ ledgerTypeLabel }}）</el-tag
            >
            <el-button type="primary" link @click="currentStep = 0"
              >更换账户</el-button
            >
          </div>
        </div>

        <ModeSelect />

        <TemplateDownloadSection />

        <UploadArea />
      </div>

      <!-- #2836：格式说明从「右侧 340px 窄栏」改为「上传区下方通栏横排」。
           窄栏里每条提示要折 3~4 行（"下载 CSV 模板填写数据，或直接上传同花顺
           等券商导出的 Excel/CSV 文件" 就占 4 行），是首屏阅读成本最高的一块；
           通栏后按 minmax(250px) 自动分栏，同样内容降到 1~2 行，卡片高度也从
           360+ 降到 130 左右。 -->
      <div v-if="formatGuides[selectedMode]" class="upload-guide">
        <FormatGuide />
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-step {
  min-height: 380px;
  padding: 0;
}

.upload-layout {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1100px;
  margin: 0 auto;
}

.upload-left {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.upload-guide {
  width: 100%;
  min-width: 0;
}

.ledger-select-area {
  margin-bottom: 0;
}
</style>
