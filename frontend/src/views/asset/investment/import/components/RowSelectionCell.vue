<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

defineProps<{ row: any }>();

const {
  isRowSelected,
  isRowBlocked,
  handleRowCheckboxChange,
  selectedLedgerLinkedCash,
  showTransferBadge,
  dismissTransferBadge
} = useImportWizardContext();

/** #2281：转账行勾选后徽章使命完成，随之消失 */
function onTransferChange(row: any, val: boolean) {
  handleRowCheckboxChange(row, val);
  dismissTransferBadge(row);
}
</script>

<template>
  <!-- #2281：转账行条件放开——已关联现金账户才可勾；未关联禁用并指路横幅 -->
  <el-tooltip
    v-if="row.is_cash_transfer && !selectedLedgerLinkedCash"
    content="请先关联现金账户（见页面上方提示）"
    placement="top"
  >
    <el-checkbox :model-value="false" disabled />
  </el-tooltip>
  <el-checkbox
    v-else-if="row.is_cash_transfer"
    :model-value="isRowSelected(row)"
    @change="(val: boolean) => onTransferChange(row, val)"
  />
  <el-checkbox
    v-else
    :model-value="isRowSelected(row)"
    :disabled="row.error || isRowBlocked(row)"
    @change="(val: boolean) => handleRowCheckboxChange(row, val)"
  />

  <!-- #2281：转账行一次性「可导入」徽章——让用户感知到能力存在（用不用由他定），
       点击或勾选本行后消失 -->
  <el-tooltip
    v-if="showTransferBadge(row)"
    :content="
      selectedLedgerLinkedCash
        ? '银证转账行支持导入：勾选后现金账户自动生成反向流水'
        : '银证转账行支持导入：关联现金账户后即可勾选'
    "
    placement="top"
  >
    <el-tag
      size="small"
      type="success"
      class="transfer-badge"
      @click.stop="dismissTransferBadge(row)"
      >可导入</el-tag
    >
  </el-tooltip>

  <el-tag v-if="row.is_calculated" size="small" type="warning" class="ml-1"
    >待确认</el-tag
  >
</template>

<style scoped>
/* #2281：徽章可点击（点击=我知道了），给一点交互暗示 */
.transfer-badge {
  margin-left: 4px;
  cursor: pointer;
}
</style>
