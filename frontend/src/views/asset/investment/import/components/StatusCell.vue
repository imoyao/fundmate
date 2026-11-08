<script setup lang="ts">
import { computed } from "vue";
import { useImportWizardContext } from "../composables/useImportWizardContext";
import type { PreviewRow } from "../composables/previewRow";
import { statusKindOf } from "../composables/statusKind";

const props = defineProps<{ row: PreviewRow }>();

const {
  isRowBlocked,
  isFeeExplained,
  isAmountMismatch,
  isMissingCode,
  feeDiffOf
} = useImportWizardContext();

/**
 * 分支判据全在 `statusKindOf`（composables/statusKind.ts），本组件只负责「怎么画」。
 * 抽出去的原因见该文件头：模板里的 `v-else` 会静默吞掉任何漏写的判据，把错账
 * 显示成绿色「正常」——而这个缺口在组件内部无法被测试钉住。
 */
const kind = computed(() =>
  statusKindOf(props.row, {
    isRowBlocked,
    isFeeExplained,
    isAmountMismatch,
    isMissingCode
  })
);

/**
 * 警告态 tooltip：差额多少、为什么不算错。
 * 与「待补全」严格区分 —— 警告可导入，阻断不可导入。
 */
const feeHint = computed(() => {
  const diff = feeDiffOf(props.row);
  return (
    `金额比「数量×单价」多/少 ${diff.toFixed(2)} 元，等于该笔手续费。` +
    `入库时成交额按数量×单价记录、手续费单独一列，成本不受影响，可直接导入`
  );
});

/**
 * 金额对不上的 tooltip（#2836）：差多少、手续费能解释多少、为什么仍放行。
 *
 * 口径**不阻断**：手续费漏项是交割单的常见情况（券商有时只列佣金、不含印花税
 * 与过户费），一刀切禁勾会让几百行需要手工放行。要的是「说得对」，不是「拦得死」。
 */
const mismatchHint = computed(() => {
  const diff = feeDiffOf(props.row);
  const fee = Math.abs(Number(props.row.fee) || 0);
  return (
    `金额与「数量×单价」相差 ${diff.toFixed(2)} 元，超出该行手续费（${fee.toFixed(2)} 元）` +
    `能解释的范围——可能是费用列漏项（只填了佣金、缺印花税或过户费），也可能是金额被改过。` +
    `仍可导入：入库时成交额按数量×单价记录，手续费单独一列。建议先回原文件核对`
  );
});
</script>

<template>
  <!-- #2836：被配对消费的行优先显示——它是「不用你管」而不是「有问题」，
       不能落到下面的正常/待补全分支里被误读 -->
  <el-tooltip
    v-if="kind === 'consumed'"
    content="同日的债券兑付已经把份额清掉了（兑付自动清仓），这行只是券商附带的份额转移记录，不会重复入账"
    placement="top"
  >
    <el-tag type="info" size="small">已随兑付清仓</el-tag>
  </el-tooltip>
  <el-tooltip
    v-else-if="kind === 'linkWarning'"
    :content="row.link_warning"
    placement="top"
  >
    <el-tag type="warning" size="small">税有疑问</el-tag>
  </el-tooltip>
  <el-tooltip
    v-else-if="kind === 'duplicate'"
    content="该交易已存在于系统中，默认跳过。如需强制导入，请手动勾选"
    placement="top"
  >
    <el-tag type="warning" size="small">重复</el-tag>
  </el-tooltip>
  <el-tag v-else-if="kind === 'error'" type="danger" size="small">错误</el-tag>
  <!-- #2836：与「金额不符」同一批补上的分支。代码未匹配的行原先也一路落到
       「正常」——它是 fix 分类里最容易漏配标签的一档，因为行本身字段齐全。 -->
  <el-tooltip
    v-else-if="kind === 'missingCode'"
    content="券商给的标的代码不在你的产品库里，导入前需要先匹配到已有产品或新建"
    placement="top"
  >
    <el-tag type="warning" size="small">代码未匹配</el-tag>
  </el-tooltip>
  <el-tag v-else-if="kind === 'blocked'" type="info" size="small"
    >待补全</el-tag
  >
  <!-- #2836：这个分支曾经不存在，于是金额对不上的行落到末尾的「正常」绿色标签，
       而概览条与修正面板都在说它有问题。 -->
  <el-tooltip
    v-else-if="kind === 'mismatch'"
    :content="mismatchHint"
    placement="top"
  >
    <el-tag type="warning" size="small">金额不符</el-tag>
  </el-tooltip>
  <!-- #2836 后续（2026-11-08）：差额被手续费解释 = 数据是对的，只是解释
       「为什么金额 ≠ 数量×单价」。它归「数据完整」可导入（概览条不计入
       需要修正），故不与 重复/金额不符 等真问题共用 warning 黄——用户把
       黄读成 warning，会以为这笔有错。info 档：需要看一眼，但不是问题；
       也不用 success：绿色会让用户以为金额严丝合缝，而差额确实存在。 -->
  <el-tooltip
    v-else-if="kind === 'feeExplained'"
    :content="feeHint"
    placement="top"
  >
    <el-tag type="info" size="small">含手续费</el-tag>
  </el-tooltip>
  <!-- 推算出来的行（缺价格用净值补、缺数量用金额反算）：肯定不算「正常」，
       但也不缺字段，所以不能落进「待补全」。原先这枚标签挂在勾选列，与状态列
       的「待补全」并排出现两枚，勾选列只有 50px 也被撑变形（#2836）。 -->
  <el-tooltip
    v-else-if="kind === 'calculated'"
    content="缺少的字段已按可得数据推算（如用确认净值补单价），导入前请确认一眼"
    placement="top"
  >
    <el-tag type="warning" size="small">待确认</el-tag>
  </el-tooltip>
  <el-tag v-else type="success" size="small">正常</el-tag>
</template>
