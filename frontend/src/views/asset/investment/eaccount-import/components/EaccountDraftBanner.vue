<template>
  <!-- #1239 草稿层：同域（A）E账户导入草稿恢复 Banner，不弹窗打断 -->
  <div
    v-if="p.draftBannerVisible && p.pendingDraftMeta"
    class="draft-banner"
    role="alert"
  >
    <IconifyIconOffline icon="ep:edit-pen" class="draft-banner__icon" />
    <div class="draft-banner__text">
      发现未完成的 E账户导入草稿（{{ p.pendingDraftMeta.rowCount }} 条持仓），
      是否继续？
    </div>
    <div class="draft-banner__actions">
      <el-button size="small" type="primary" @click="p.restoreDraft">
        恢复草稿
      </el-button>
      <el-button size="small" text @click="p.discardCurrentDraft">
        丢弃
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
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
/* ===== #1239 草稿恢复 Banner：中性信息色，非红非弹窗（柔性原则） ===== */
.draft-banner {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: var(--text-small);
  color: var(--text-secondary);
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.draft-banner__icon {
  font-size: 16px;
  color: var(--brand-700);
}

.draft-banner__text {
  flex: 1;
}

.draft-banner__actions {
  display: flex;
  gap: 8px;
}
</style>
