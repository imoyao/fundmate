<template>
  <!--
    对账中心页头：统一走 PageHeaderBar（design.md「一层页头」）。
    `.workbench-head` / `__title` / `__subtitle` 由 PageHeaderBar 的锚点类名承接，
    老 e2e 的不重挂载探针仍打在同一个真实 DOM 上，不需要为兼容再造一层标题。

    主按钮按 D3 改名「重新检查持仓差异」：原「运行对账」只跑域 B，
    标签承诺全量、实现只跑一类，属于文案骗人。
  -->
  <PageHeaderBar
    class="workbench-head"
    title="对账中心"
    subtitle="统一处理 E账户对账，把账上不一致、记录不全的地方集中核对并修好"
    title-class="workbench-head__title"
    subtitle-class="workbench-head__subtitle"
    :updated-at="updatedAt"
  >
    <template #action>
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
        重新检查持仓差异
      </el-button>
    </template>
  </PageHeaderBar>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";

defineOptions({ name: "WorkbenchHead" });

/**
 * 页头只持有展示态：`running` 是按钮进行中态，`updatedAt` 是数据日期胶囊。
 * 动作一律上抛，本组件不读 composable、不碰路由。
 */
withDefaults(
  defineProps<{
    running: boolean;
    /** 最近一次对账数据日期，空串时 PageHeaderBar 不渲染胶囊 */
    updatedAt?: string;
  }>(),
  { updatedAt: "" }
);

const emit = defineEmits<{
  (e: "recognize"): void;
  (e: "run"): void;
}>();
</script>
