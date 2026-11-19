<!--
  MaturitySettleGuide · 逆回购「到期了，现在结清吗」的引导（#931 / D114）

  场景：用户在持仓明细里把逆回购的到期日改成今天或更早。这一步**已经**让这笔钱从
  「投资」挪到了「现金」（后端 `effective_count_as_investment` 用 `as_of < maturity`），
  但流水还停在「只有买入」的孤儿态——表格标红只说明「已到期」，用户仍得自己找到
  页面上方「类现金」卡片的「到期回款」按钮。中间这一步没有任何提示，于是最常见的结果
  是持仓写着「已到期」、钱却一直没结清。

  复用 `LedgerReverseRepoSettleDialog`（同一条 `POST /cash-like/reverse-repo/settle/`
  与同一套 D114 口径），不新写第二个结清表单：整笔结清、利息单独成行、重复提交由后端拒。

  判据全在 `positionMaturity.dueSettleCandidate`（纯函数、有单测）：品类是逆回购、
  到期日不晚于今天、类现金明细里还有在途本金——缺任一条都**不弹**。尤其是
  `net_amount > 0`：已经结清过还弹，后端只会回「没有在途本金」。
-->
<template>
  <LedgerReverseRepoSettleDialog
    v-model="visible"
    :ledger-id="ledgerId"
    :rows="selectedRows"
    :initial-symbol="initialSymbol"
    @settled="onSettled"
  />
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessageBox } from "element-plus";
import LedgerReverseRepoSettleDialog from "./LedgerReverseRepoSettleDialog.vue";
import { dueSettleCandidate } from "./positionMaturity";
import type { CashLikeBreakdownRow } from "@/composables/ledger/types";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";

defineOptions({ name: "MaturitySettleGuide" });

// 与同目录各面板同一模式：页面 state 以整对象传入，reactive 代理后模板里直接绑，
// 不必把每个 ref 拆成单独 prop（这里只需要 ledgerId / 概览明细 / 两个 reload）。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
const p = reactive(props.page);

const visible = ref(false);
const initialSymbol = ref("");
const selectedRows = ref<CashLikeBreakdownRow[]>([]);

const ledgerId = computed(() => Number(p.ledgerId));

/**
 * 保存到期日后调用。命中判据就弹确认；用户点「登记回款」才打开结清弹窗。
 *
 * 确认框而非直接弹结清表单：到期日填错了也会走到这里（改成过去日期本身就是常见误操作），
 * 上来就让填本金与回款日，等于把误操作直接推到一次真实写库之前。
 */
async function maybePrompt(
  row: { asset_type?: string; symbol?: string },
  maturityDate: string | null
) {
  const candidate = dueSettleCandidate({
    assetType: row.asset_type,
    symbol: row.symbol,
    maturityDate,
    rows: p.summaryData?.cash_like_breakdown ?? []
  });
  if (!candidate) return;
  try {
    await ElMessageBox.confirm(
      "该到期日已过，这笔逆回购已转为现金、不再计入投资。现在登记到期回款吗？",
      "到期回款",
      {
        confirmButtonText: "登记回款",
        cancelButtonText: "稍后",
        type: "warning"
      }
    );
  } catch {
    // 取消 = 什么都不做。稍后仍可从上方「类现金」卡片进同一入口
    return;
  }
  selectedRows.value = [candidate];
  initialSymbol.value = candidate.symbol ?? "";
  visible.value = true;
}

/** 结清会同时改变在途本金与类现金余额：两者都要重取（只刷一个，页面两个数字会打架） */
function onSettled() {
  p.loadSummary();
  p.loadHoldings();
}

// 父组件在保存成功后调用；没有默认动作，不做成 emits 是为了避免「保存 → 弹窗」的
// 时序再走一遍事件链（父组件已经拿到了这次保存的结果，再绕一圈只会多一个状态）。
defineExpose({ maybePrompt });
</script>
