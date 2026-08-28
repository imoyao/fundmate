<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import AccountFormFields from "./AccountFormFields.vue";
import {
  createLedger,
  type SalesInstitution,
  type LedgerItem
} from "@/api/ledger";
import type { PortfolioItem } from "@/api/portfolio";

/**
 * 新建账户对话框（#984 ledgers/index.vue 拆分）。
 * 从 index.vue 原样迁移：表单结构、AccountFormFields 接线、创建逻辑不变；
 * 现金账户/组合/销售机构候选由父页面传入（父页面 fetchData 已统一加载）。
 */
const props = defineProps<{
  visible: boolean;
  cashLedgers: LedgerItem[];
  portfolioList: PortfolioItem[];
  salesInstitutions: SalesInstitution[];
  /** 打开时预置的账户类型（#1082 入口预填）；缺省 stock，默认行为不回归 */
  initialLedgerType?: string;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  /** 创建成功，父页面刷新列表 */
  created: [];
}>();

const creating = ref(false);
// 表单的 ledger_type 字段此处承载「渠道分组」值（bank/securities/fund_platform/...），
// 提交时作为 channel_category 下发，后端据其派生真实 ledger_type。
const createForm = ref({
  name: "",
  ledger_type: "bank",
  notes: "",
  linked_cash_ledger_id: null as number | null,
  // 类现金产品绑定（#1137）：基金代码 + 自动申购开关（默认关闭）
  linked_money_fund_code: null as string | null,
  auto_purchase_money_fund: false,
  portfolio_id: null as number | null,
  fee_config: null as any,
  sales_institution_id: null as number | null
});

// 每次打开重置表单（原 openCreateDialog 的重置语义迁移至此）；
// ledger_type 取外部预置渠道分组（分组入口预填），未指定时维持默认 bank
watch(
  () => props.visible,
  val => {
    if (val) {
      createForm.value = {
        name: "",
        ledger_type: props.initialLedgerType || "bank",
        notes: "",
        linked_cash_ledger_id: null,
        linked_money_fund_code: null,
        auto_purchase_money_fund: false,
        portfolio_id: null,
        fee_config: null,
        sales_institution_id: null
      };
    }
  }
);

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  creating.value = true;
  try {
    // 下发 channel_category（由表单 ledger_type 字段承载），后端据其派生 ledger_type
    await createLedger({
      name: createForm.value.name,
      channel_category: createForm.value.ledger_type,
      notes: createForm.value.notes,
      linked_cash_ledger_id: createForm.value.linked_cash_ledger_id,
      linked_money_fund_code: createForm.value.linked_money_fund_code,
      auto_purchase_money_fund: createForm.value.auto_purchase_money_fund,
      portfolio_id: createForm.value.portfolio_id,
      fee_config: createForm.value.fee_config,
      sales_institution_id: createForm.value.sales_institution_id
    });
    ElMessage.success("账户创建成功");
    emit("update:visible", false);
    emit("created");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="创建账户"
    width="420px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form :model="createForm" label-width="100px">
      <el-form-item label="账户名称" required>
        <el-input
          v-model="createForm.name"
          placeholder="如：华泰证券、招商银行"
        />
      </el-form-item>

      <AccountFormFields
        v-model:ledger-type="createForm.ledger_type"
        v-model:linked-cash-id="createForm.linked_cash_ledger_id"
        v-model:linked-money-fund-code="createForm.linked_money_fund_code"
        v-model:auto-purchase-money-fund="createForm.auto_purchase_money_fund"
        v-model:portfolio-id="createForm.portfolio_id"
        v-model:fee-config="createForm.fee_config"
        v-model:sales-institution-id="createForm.sales_institution_id"
        :cash-ledgers="cashLedgers"
        :portfolio-list="portfolioList"
        :sales-institutions="salesInstitutions"
      />

      <el-form-item label="备注">
        <el-input v-model="createForm.notes" placeholder="可选" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="creating" @click="handleCreate"
        >确认创建</el-button
      >
    </template>
  </el-dialog>
</template>
