<script setup lang="ts">
// 修正面板的两个附属弹窗：【查看已填充数据】与【查看转换结果】（逆回购）。
// 放一起是因为它们共享 `.bf-dialog-note` 一条说明样式，且都属于「看一眼但不改数据」。
import { filledFieldsLabel, allocationLabelOf } from "./batchFixPanelModel";
import { canRestoreSmartFilledPrice } from "../composables/smartFillPrice";
import { asPreviewRow } from "../composables/previewRow";
import type { PreviewRow } from "../composables/previewRow";

defineProps<{
  /** 已填充行（数量 / 单价由金额推算出来的那些） */
  filledRows: PreviewRow[];
  /** 解析期自动识别的逆回购行 */
  reverseRepoRows: PreviewRow[];
  /** 逆回购识别依据（由向导上下文提供，保持单一实现） */
  detectBasis: (row: PreviewRow) => string;
}>();

const filledVisible = defineModel<boolean>("filled-visible", {
  required: true
});
const repoVisible = defineModel<boolean>("repo-visible", { required: true });

/** #2902：装载期补价可逐行退回；批量修正的填充仍走顶部【撤销上一步】 */
const emit = defineEmits<{
  "restore-original": [row: PreviewRow];
}>();
</script>

<template>
  <el-dialog
    v-model="filledVisible"
    title="已填充数据"
    width="720px"
    class="bf-dialog"
  >
    <el-table :data="filledRows" size="small" max-height="400">
      <el-table-column label="名称" prop="name" min-width="140" />
      <el-table-column label="代码" prop="symbol" width="100" />
      <el-table-column label="已填充字段" min-width="110">
        <template #default="{ row }">
          {{ filledFieldsLabel(asPreviewRow(row)) }}
        </template>
      </el-table-column>
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="单价" prop="price" width="110" />
      <el-table-column label="操作" width="110">
        <template #default="{ row }">
          <el-button
            v-if="canRestoreSmartFilledPrice(row)"
            link
            type="primary"
            size="small"
            @click="emit('restore-original', asPreviewRow(row))"
          >
            恢复原始值
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <p class="bf-dialog-note">
      数量 / 价格按「金额 ÷
      另一项」自动推算。上传期补价可点【恢复原始值】退回你上传时的原值；
      批量修正产生的填充由顶部【撤销上一步】回滚。
    </p>
  </el-dialog>

  <el-dialog
    v-model="repoVisible"
    title="逆回购转换结果"
    width="720px"
    class="bf-dialog"
  >
    <p class="bf-dialog-note">
      解析规则：沪市 204xxx、深市 1318xx 代码自动识别为逆回购，配置目标自动设为
      「活钱」。类型识别是解析事实不可撤销；配置目标可在分区点【撤销】回退为「长期增值」。
    </p>
    <el-table :data="reverseRepoRows" size="small" max-height="400">
      <el-table-column label="日期" prop="trade_date" width="110" />
      <el-table-column label="代码" prop="symbol" width="90" />
      <el-table-column label="名称" prop="name" min-width="120" />
      <el-table-column label="金额" prop="amount" width="110" />
      <el-table-column label="识别依据" min-width="110">
        <template #default="{ row }">
          {{ detectBasis(asPreviewRow(row)) }}
        </template>
      </el-table-column>
      <el-table-column label="配置目标" width="110">
        <template #default="{ row }">
          {{ allocationLabelOf(row.allocation) }}
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<style scoped>
.bf-dialog-note {
  margin: 8px 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
