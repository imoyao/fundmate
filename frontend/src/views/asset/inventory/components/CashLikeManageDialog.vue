<template>
  <el-dialog
    :model-value="visible"
    title="管理账外类现金流水"
    width="1000px"
    top="6vh"
    @update:model-value="v => emit('update:visible', v)"
  >
    <el-alert type="info" :closable="false" show-icon class="mb-3">
      <template #title>口径说明</template>
      货币基金 /
      逆回购按<strong>流水净额</strong>记账，不建持仓行，因此不在「持仓明细」表里。
      这里的金额<strong>已计入总资产</strong>，本弹窗只做管理，不会再加进任何持仓合计。
    </el-alert>

    <div class="toolbar">
      <el-input
        v-model="m.query"
        placeholder="搜索产品名称 / 代码"
        clearable
        class="toolbar__search"
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-checkbox
        v-model="m.includeReconciled"
        label="包含已归置"
        @change="onSearch"
      />
      <el-button size="small" @click="onSearch">搜索</el-button>
      <el-button size="small" type="primary" plain @click="m.openCreate()">
        补录流水
      </el-button>
      <el-button size="small" @click="m.openReconcile('attach')"
        >归置到持仓</el-button
      >
      <el-button size="small" @click="m.openReconcile('detach')"
        >撤销归置</el-button
      >
      <span class="toolbar__count"
        >共 {{ m.total }} 笔 · 已选 {{ m.selectedIds.length }} 笔</span
      >
    </div>

    <el-table
      v-loading="m.loading"
      :data="m.flows"
      height="420"
      size="small"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="42" />
      <el-table-column label="产品" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span>{{ row.position_name || "未命名" }}</span>
          <span v-if="row.symbol" class="cell-sub"> {{ row.symbol }}</span>
          <el-tag
            v-if="row.symbol_inferred"
            size="small"
            type="warning"
            class="ml-1"
          >
            代码·推断
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ row.asset_type_label }}</template>
      </el-table-column>
      <el-table-column label="动作" width="100">
        <template #default="{ row }">{{
          TXN_LABELS[row.txn_type] || row.txn_type
        }}</template>
      </el-table-column>
      <el-table-column label="金额(元)" width="120" align="right">
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.amount"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <el-table-column label="入桶" width="80">
        <template #default="{ row }">
          {{
            row.bucket === "income"
              ? "收益"
              : row.bucket === "net"
                ? "本金"
                : "不计"
          }}
        </template>
      </el-table-column>
      <el-table-column label="确认日" width="108">
        <template #default="{ row }">{{ row.confirm_date || "—" }}</template>
      </el-table-column>
      <el-table-column label="交易日" width="108">
        <template #default="{ row }">{{ row.trade_date || "—" }}</template>
      </el-table-column>
      <el-table-column label="来源" width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ row.source || "—" }}</template>
      </el-table-column>
      <el-table-column label="归置状态" min-width="170" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.reconciled">
            已由持仓「{{
              row.reconciled.position_name || row.reconciled.position_id
            }}」体现
          </span>
          <span v-else class="cell-sub">账外（未归置）</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="m.openEdit(row as CashLikeFlow)">
            编辑
          </el-button>
          <el-button
            text
            size="small"
            type="danger"
            @click="m.remove(row as CashLikeFlow)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="m.page"
        :page-size="m.perPage"
        :total="m.total"
        layout="prev, pager, next, total"
        small
        @current-change="m.load"
      />
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>

  <CashLikeFlowForm
    v-model:visible="m.formVisible"
    :mode="m.editing ? 'edit' : 'create'"
    :flow="m.editing"
    :ledger-id="ledgerId"
    :targets="m.targets"
    :submitting="m.submitting"
    @submit-create="m.submitCreate"
    @submit-edit="m.submitEdit"
  />

  <el-dialog
    :model-value="m.reconcileVisible"
    :title="m.reconcileAction === 'attach' ? '归置到持仓' : '撤销归置'"
    width="480px"
    append-to-body
    @update:model-value="v => (m.reconcileVisible = v)"
  >
    <template v-if="m.reconcileAction === 'attach'">
      <p class="reconcile-tip">
        归置表达「这批流水已由某持仓体现」：只把流水的
        <code>position_id</code>
        指向目标持仓，金额、交易日、代码与去重键都不改。
        归置后它们退出账外类现金净额，<strong>不再被算成两笔钱</strong>。
      </p>
      <el-select
        v-model="m.targetId"
        placeholder="选择目标持仓"
        filterable
        style="width: 100%"
      >
        <el-option
          v-for="t in m.targets"
          :key="t.id"
          :label="`${t.name}（${t.symbol || '无代码'}）`"
          :value="t.id"
        />
      </el-select>
      <p class="reconcile-tip">
        不做代码硬匹配：账本 12 的 153
        笔同款流水大多没有代码，靠你在这里显式指定目标。
      </p>
    </template>
    <p v-else class="reconcile-tip">
      撤销后流水重回账外类现金，净额重新计入类现金合计。
    </p>
    <template #footer>
      <el-button @click="m.reconcileVisible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="m.submitting"
        @click="m.submitReconcile"
      >
        确认
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 账外类现金流水管理弹窗：账户详情「类现金」卡片、全面盘点「类现金」表、
 * 「持仓明细」搜索命中三处共用同一写入口（口径单一真相源）。
 *
 * 归置与「到期回款」是本次补的两个前提：
 * - 153 笔同款孤儿流水与 247 号持仓并存，不归置会被误读成两笔钱；
 * - 4 笔逆回购全是 buy，不补回款净额就是永远只增不减的在途额。
 */
import { reactive, toRef, watch } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { CashLikeFlow } from "@/api/cashLike";
import { useCashLikeManage } from "../composables/useCashLikeManage";
import CashLikeFlowForm from "./CashLikeFlowForm.vue";

defineOptions({ name: "CashLikeManageDialog" });

const props = defineProps<{
  visible: boolean;
  ledgerId: number | null;
  seedQuery?: string;
}>();

const emit = defineEmits<{
  (e: "update:visible", v: boolean): void;
  (e: "changed"): void;
}>();

const TXN_LABELS: Record<string, string> = {
  buy: "买入 / 申购",
  sell: "卖出 / 赎回",
  withdraw: "取出",
  deposit: "存入",
  dividend: "分红",
  dividend_cash: "收益到账",
  dividend_tax: "代扣税",
  split: "份额拆分"
};

const m = reactive(
  useCashLikeManage(toRef(props, "ledgerId"), () => emit("changed"))
);

watch(
  () => props.visible,
  shown => {
    if (shown) void m.open(props.seedQuery || "");
    else m.close();
  }
);

function onSearch() {
  m.page = 1;
  void m.load();
}

function onSelectionChange(rows: CashLikeFlow[]) {
  m.selectedIds = rows.map(r => r.id);
}
</script>

<style scoped lang="scss">
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.toolbar__search {
  width: 220px;
}

.toolbar__count {
  margin-left: auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.cell-sub {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.reconcile-tip {
  margin: 0 0 12px;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}
</style>
