<script setup lang="ts">
import Superellipse from "@/components/Superellipse/index.vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { selectedMode, availableModes, logoBrokenMap, onLogoError } =
  useImportWizardContext();
</script>

<template>
  <div>
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
  </div>
</template>

<style scoped>
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
</style>
