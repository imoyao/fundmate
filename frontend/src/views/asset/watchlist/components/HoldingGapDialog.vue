<!--
  HoldingGapDialog · 持仓未入自选「明细」弹窗（#1458 后续：持仓即自选）

  与 HoldingGapBanner 的分工：横幅内联前 3 条（缺口少时零点击即读），超出部分
  由本弹窗承载——缺口可能有几十个（批量导入后），必须限高滚动，不能把横幅撑成一堵墙。

  这里只做「看清楚 + 一键补齐」两件事，不做逐条勾选/单条加入：
  缺口的定义是「**有活跃持仓**却没进自选」，用户本来就该全部补齐；后端
  POST /api/watchlist/reconcile/ 也只提供全量补齐，没有按 symbol 的子集接口，
  在前端伪造「单条加入」只会做出一半不可用的交互。

  props：modelValue(显隐)、gaps(缺口列表)、reconciling(补齐进行中)。
  emits：update:modelValue、add-all（由宿主执行补齐并刷新）。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="尚未加入自选的持仓产品"
    width="640px"
    class="holding-gap-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="gap-dialog__hint">
      以下 {{ gaps.length }} 个持仓产品还没进自选，因此无法打标签 / 写备注。
      「持仓即自选」：补齐后可像普通自选一样管理，卖出后也不会被删除。
    </p>

    <el-table :data="gaps" :max-height="360" size="small" class="gap-table">
      <el-table-column label="品类" width="96">
        <template #default="{ row }">
          <!-- row 为 EP 的 DefaultRow（结构化类型无法直接收窄），就地取 asset_type；
               标签仍走 assetTypeLabel（后端 /enums 单一真相源，禁止手抄映射） -->
          <AssetTypeBadge
            v-if="row.asset_type"
            :type="row.asset_type"
            :label="row.asset_type ? assetTypeLabel(row.asset_type) : ''"
          />
        </template>
      </el-table-column>
      <el-table-column label="名称" min-width="200">
        <template #default="{ row }">
          <span class="gap-table__name" :title="row.name">{{
            row.name || row.symbol
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="编码" width="150">
        <template #default="{ row }">
          <span class="gap-table__code"># {{ row.symbol }}</span>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button type="primary" :loading="reconciling" @click="emit('add-all')">
        一键加入自选
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import type { HoldingGap } from "@/api/types";

defineOptions({ name: "HoldingGapDialog" });

defineProps<{
  modelValue: boolean;
  gaps: HoldingGap[];
  reconciling: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "add-all"): void;
}>();
</script>

<style scoped>
.gap-dialog__hint {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 名称单行截断 + title 兜全名：批量导入的全称可能很长，不能撑破列宽 */
.gap-table__name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
}

.gap-table__code {
  font-family: var(--font-number);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}
</style>
