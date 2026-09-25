<template>
  <div class="eaccount-import-page">
    <!-- 页头 -->
    <header class="import-head">
      <div class="import-head__text">
        <h1 class="import-head__title">导入 E账户快照</h1>
        <p class="import-head__subtitle">
          上传 E账户（中国结算）导出的持仓文件，解析后自动与各销售渠道对账归因
        </p>
      </div>
      <el-button
        v-if="currentStep === 1"
        text
        :style="{ color: 'var(--text-secondary)' }"
        @click="goToReconcileCenter"
      >
        <IconifyIconOffline icon="ep:files" class="mr-1" />
        前往对账中心
      </el-button>
    </header>

    <!-- #1239 草稿层：同域（A）E账户导入草稿恢复 Banner，不弹窗打断 -->
    <EaccountDraftBanner :page="imp" />

    <!-- 两步流程指示（与交易导入向导同语言） -->
    <el-steps
      :active="currentStep"
      finish-status="success"
      align-center
      class="import-steps"
    >
      <el-step
        v-for="(step, index) in STEPS"
        :key="index"
        :title="step.title"
      />
    </el-steps>

    <!-- ── 步骤一：上传与预览 ── -->
    <template v-if="currentStep === 0">
      <!-- 导入方式分段控制：文件上传 / AI 识别（仅解析成功前置入口，解析后让位预览） -->
      <div v-if="!parsedOk" class="import-mode-switch" role="tablist">
        <button
          type="button"
          role="tab"
          class="import-mode-switch__item"
          :class="{ 'is-active': importMode === 'file' }"
          @click="switchMode('file')"
        >
          上传文件
        </button>
        <button
          type="button"
          role="tab"
          class="import-mode-switch__item"
          :class="{ 'is-active': importMode === 'ai' }"
          @click="switchMode('ai')"
        >
          AI 识别持仓
        </button>
      </div>

      <!-- AI 识别模式入口：文本 / 图片 → holding_import → 持仓预览行（逻辑见 components/EaccountAiPanel） -->
      <EaccountAiPanel v-if="!parsedOk && importMode === 'ai'" :page="imp" />

      <!-- 大上传卡片 + 解析完成状态条（显隐条件在组件内，与拆分前逐字一致） -->
      <EaccountUploadCard :page="imp" />

      <!-- 解析预览：只读展示，error 行标红禁提交 -->
      <EaccountParsePreview v-if="previewRows.length > 0" :page="imp" />
    </template>

    <!-- ── 步骤二：对账结果 ── -->
    <EaccountReconcileResult v-else-if="result" :page="imp" />
  </div>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";
import EaccountDraftBanner from "./components/EaccountDraftBanner.vue";
import EaccountAiPanel from "./components/EaccountAiPanel.vue";
import EaccountUploadCard from "./components/EaccountUploadCard.vue";
import EaccountParsePreview from "./components/EaccountParsePreview.vue";
import EaccountReconcileResult from "./components/EaccountReconcileResult.vue";
import { useEaccountImport } from "./composables/useEaccountImport";

defineOptions({ name: "InvestmentEaccountImport" });

// #980 P1-B 结构拆分：状态与动作收敛在 composables/useEaccountImport.ts，
// 五个子组件经 page prop 注入同一实例；index 只保留编排用的少量状态
// （解构后在模板内自动解包 ref，绑定表达式与拆分前逐字一致）。
const imp = useEaccountImport();
const {
  STEPS,
  currentStep,
  parsedOk,
  importMode,
  previewRows,
  result,
  switchMode,
  goToReconcileCenter
} = imp;
</script>

<style scoped>
/* 页面根容器：字体继承全局 token + 全页数字等宽（design.md「数字等宽对齐落地规范」） */
.eaccount-import-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* ===== 页头 ===== */
.import-head {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-standard);
}

.import-head__title {
  margin: 0;
  font-size: var(--text-display);
  font-weight: 300;
  line-height: 1.3;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.import-head__subtitle {
  margin: 6px 0 0;
  font-size: var(--text-small);
  line-height: 1.5;
  color: var(--text-secondary);
}

.import-steps {
  margin-bottom: var(--space-loose);
}

/* ===== 导入方式分段控制（上传文件 / AI 识别） ===== */
.import-mode-switch {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  margin-bottom: var(--space-standard);
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}

.import-mode-switch__item {
  padding: 6px 16px;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  transition: all 0.15s ease;
}

.import-mode-switch__item:hover {
  color: var(--text-primary);
}

.import-mode-switch__item.is-active {
  color: var(--text-inverse);
  background: var(--brand-600);
  box-shadow: var(--shadow-raised);
}
</style>
