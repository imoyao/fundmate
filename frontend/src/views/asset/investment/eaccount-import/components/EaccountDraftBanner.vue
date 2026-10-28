<template>
  <!-- #1239 草稿层：同域（A）导入持仓快照的草稿恢复 Banner，不弹窗打断。
       #2716 起壳由 SoftBanner 承担；class 保留 e2e 锚点（eaccount-draft / import-draft spec） -->
  <SoftBanner
    v-if="p.draftBannerVisible && p.pendingDraftMeta"
    class="draft-banner"
    variant="info"
    icon="ep:edit-pen"
  >
    <div class="draft-banner__text">
      发现未完成的导入草稿（{{ p.pendingDraftMeta.rowCount }} 条持仓），
      是否继续？
    </div>
    <template #actions>
      <el-button size="small" type="primary" @click="p.restoreDraft">
        恢复草稿
      </el-button>
      <el-button size="small" text @click="p.discardCurrentDraft">
        丢弃
      </el-button>
    </template>
  </SoftBanner>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import type { useEaccountImport } from "../composables/useEaccountImport";

defineOptions({ name: "EaccountDraftBanner" });

const props = defineProps<{ page: ReturnType<typeof useEaccountImport> }>();

/**
 * 共享状态单体（useEaccountImport）的响应式视图：
 * reactive 会解包嵌套 ref，模板内可直接读值、写回同一实例（#980 P1-A 同款）。
 * v-if 条件与拆分前逐字一致，false 时渲染占位注释节点，与原结构等价。
 */
const p = reactive(props.page);
</script>

<style scoped>
/* #2716 起壳由 SoftBanner info variant 承担，只保留正文文字排版 */
.draft-banner__text {
  flex: 1;
  font-size: var(--text-small);
  color: var(--text-secondary);
}
</style>
