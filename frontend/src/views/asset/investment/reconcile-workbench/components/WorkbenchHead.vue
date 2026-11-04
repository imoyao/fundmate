<template>
  <!-- 页头：标题 + 副标题 + 两个动作（AI 识别 / 运行对账）。
       状态与动作全部由父级持有（running 走 prop，点击走上抛），本组件不读
       composable、不碰路由。 -->
  <header class="workbench-head">
    <div class="workbench-head__text">
      <h1 class="workbench-head__title">对账中心</h1>
      <p class="workbench-head__subtitle">
        统一处理 E账户对账、持仓快照一致性、对账单导入的差异与补充
      </p>
    </div>
    <div class="workbench-head__actions">
      <el-button size="small" @click="emit('recognize')">
        <IconifyIconOffline icon="ep:magic-stick" class="mr-1" />
        AI 识别
      </el-button>
      <el-button
        size="small"
        type="primary"
        :loading="running"
        @click="emit('run')"
      >
        <IconifyIconOffline icon="ep:refresh-right" class="mr-1" />
        运行对账
      </el-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 对账中心页头（#980 批 B3 拆分自 reconcile-workbench/index.vue，
 * 零视觉/行为变更）：标题 / 副标题 / 「AI 识别」/「运行对账」两枚按钮，
 * 四个 style 块随模板一并迁入，scoped 作用域不变。
 */
defineProps<{
  /** 「运行对账」的进行中态（按钮 loading，父级持有 running） */
  running: boolean;
}>();

const emit = defineEmits<{
  /** 打开 AI 识别入口弹窗 */
  (e: "recognize"): void;
  /** 运行一次对账 */
  (e: "run"): void;
}>();
</script>

<style scoped>
/* 页头 */
.workbench-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.workbench-head__title {
  margin: 0 0 6px;
  font-size: var(--text-display);
  font-weight: 300;
  color: var(--text-primary);
}

.workbench-head__subtitle {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.workbench-head__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
