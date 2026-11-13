<!--
  LedgerCashLikeSettle · 账户详情页「类现金」区块的到期回款操作

  #3087 / D114 的受限回款端点原本只接在「全面盘点」页（CashLikeTable）；账户详情页
  能看到 R-007 / GC007 这类只有买入的逆回购孤儿流水，却没有任何结清入口，用户看到
  的就是「这些产品还是无法卖出」。这里把同一条端点接到本页标题行的 #action 槽。
  拆成独立组件是为了让 LedgerCashLikeCard 不越过 400 行体量门禁，也让「回款」这件事
  的判据、状态、弹窗只留一处（卡片只负责传明细与转出 saved）。
-->
<template>
  <div class="cash-like-settle">
    <el-button
      v-if="candidates.length"
      size="small"
      type="primary"
      plain
      @click="openSettle"
    >
      到期回款
    </el-button>
    <LedgerReverseRepoSettleDialog
      v-model="dialogVisible"
      :ledger-id="ledgerId"
      :rows="candidates"
      :initial-symbol="initialSymbol"
      @settled="emit('saved')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import LedgerReverseRepoSettleDialog from "./LedgerReverseRepoSettleDialog.vue";
import type { CashLikeBreakdownRow } from "@/composables/ledger/types";

defineOptions({ name: "LedgerCashLikeSettle" });

const props = defineProps<{
  /** 目标账户 id；缺失时不挂弹窗（回款行必须落在账户上） */
  ledgerId?: number;
  /** 账外类现金逐产品明细 */
  rows: CashLikeBreakdownRow[];
}>();

const emit = defineEmits<{
  /** 回款已写入（调用方刷新账户概览） */
  saved: [];
}>();

/**
 * 能否登记回款：与后端 `cash_like_settle.outstanding_cents` 同判据——
 * 逆回购、仍有在途本金、有标的代码。货基没有到期（赎回走申购/赎回流水），
 * 净额归零的逆回购再点只会被后端拒，故这里就不给按钮。
 */
function canSettle(row: CashLikeBreakdownRow): boolean {
  return (
    row.asset_type === "reverse_repo" && row.net_amount > 0 && !!row.symbol
  );
}

const candidates = computed(() => props.rows.filter(canSettle));
const dialogVisible = ref(false);
const initialSymbol = ref("");

function openSettle() {
  initialSymbol.value = "";
  dialogVisible.value = true;
}
</script>

<style scoped lang="scss">
/* 标题行 #action 槽里的一个 flex item；弹窗经 teleport 挂到 body，不占布局 */
.cash-like-settle {
  display: inline-flex;
}
</style>
