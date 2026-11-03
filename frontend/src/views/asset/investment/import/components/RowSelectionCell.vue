<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

defineProps<{ row: any }>();

const {
  isRowSelected,
  isRowBlocked,
  handleRowCheckboxChange,
  selectedLedgerLinkedCash
} = useImportWizardContext();
</script>

<template>
  <!-- #2836：被配对规则消费的行（如兑付附带的「股份转出」）不入账，不可勾选。
       它必须还看得见——凭空消失会让用户怀疑数据丢了；也正因为看得见，
       才需要把「为什么不入账」写在 tooltip 里。 -->
  <el-tooltip
    v-if="row.consumed_by"
    content="该行效果已由同日的债券兑付覆盖（兑付本身已清仓），无需重复入账"
    placement="top"
  >
    <el-checkbox :model-value="false" disabled />
  </el-tooltip>
  <!-- #2281：转账行条件放开——已关联现金账户才可勾；未关联禁用并指路横幅。 -->
  <!-- #2838：这里原先还有一枚每行一次的「可导入」徽章，已移除。勾选列只有
       50px，徽章必然折到第二行、再被截成「可导…」；而它要说的「转账行能导」
       已被三处同义重复表达：状态列的「正常」、这个可勾的复选框本身、页顶横幅。
       批量层面改由摘要卡「含 N 条银证转账」旁的「全选」承担。 -->
  <el-tooltip
    v-else-if="row.is_cash_transfer && !selectedLedgerLinkedCash"
    content="请先关联现金账户（见页面上方提示）"
    placement="top"
  >
    <el-checkbox :model-value="false" disabled />
  </el-tooltip>
  <el-checkbox
    v-else-if="row.is_cash_transfer"
    :model-value="isRowSelected(row)"
    @change="(val: boolean) => handleRowCheckboxChange(row, val)"
  />
  <el-checkbox
    v-else
    :model-value="isRowSelected(row)"
    :disabled="row.error || isRowBlocked(row)"
    @change="(val: boolean) => handleRowCheckboxChange(row, val)"
  />

  <!-- #2836：「待确认」（推算行）与「待补全」原先一枚在这里、一枚在状态列并排出现，
       勾选列本来只有 50px，两枚标签把它撑得歪斜。标签属于「这行是什么状态」，
       统一收到状态列（StatusCell 里已有对应分支），勾选列回归纯勾选。 -->
</template>
