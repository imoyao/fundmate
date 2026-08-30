<template>
  <el-dialog
    :model-value="visible"
    title="编辑账户"
    width="420px"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <el-form :model="editForm" label-width="100px">
      <el-form-item label="账户名称" required>
        <el-input v-model="editForm.name" />
      </el-form-item>
      <el-form-item label="配置目标">
        <el-select
          v-model="editForm.default_allocation"
          class="w-full"
          clearable
        >
          <el-option
            v-for="opt in ALLOCATION_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
      <AccountFormFields
        v-model:ledger-type="editForm.ledger_type"
        v-model:linked-cash-id="editForm.linked_cash_ledger_id"
        v-model:linked-money-fund-code="editForm.linked_money_fund_code"
        v-model:auto-purchase-money-fund="editForm.auto_purchase_money_fund"
        v-model:portfolio-id="editForm.portfolio_id"
        v-model:fee-config="editForm.fee_config"
        v-model:sales-institution-id="editForm.sales_institution_id"
        :linked-money-fund-name="accountInfo?.linked_money_fund_name ?? null"
        :cash-ledgers="cashLedgers"
        :portfolio-list="portfolioList"
        :sales-institutions="salesInstitutions"
      />
      <el-form-item label="备注">
        <el-input v-model="editForm.notes" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!isEditFormModified"
        @click="handleUpdate"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { updateLedger, type LedgerItem } from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { ALLOCATION_OPTIONS } from "@/constants";
import AccountFormFields from "./AccountFormFields.vue";
import type { SalesInstitution } from "@/api/ledger";

interface EditAccountForm {
  name: string;
  ledger_type: string;
  default_allocation: string | null;
  notes: string;
  portfolio_id: number | null;
  linked_cash_ledger_id: number | null;
  linked_money_fund_code: string | null;
  auto_purchase_money_fund: boolean;
  fee_config: Record<string, unknown> | null;
  sales_institution_id: number | null;
}

const props = defineProps<{
  visible: boolean;
  ledgerId: string;
  accountInfo: LedgerItem | null;
  ledgers: LedgerItem[];
  portfolioList: PortfolioItem[];
  salesInstitutions: SalesInstitution[];
  cashLedgers: LedgerItem[];
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  saved: [];
}>();

const editForm = ref<EditAccountForm>({
  name: "",
  ledger_type: "bank",
  default_allocation: null,
  notes: "",
  portfolio_id: null,
  linked_cash_ledger_id: null,
  linked_money_fund_code: null,
  auto_purchase_money_fund: false,
  fee_config: null,
  sales_institution_id: null
});

const editFormSnapshot = ref("");
const saving = ref(false);

// 表单未改动时禁用「保存」，避免无意义的提交（#交互修复）
const isEditFormModified = computed(
  () => JSON.stringify(editForm.value) !== editFormSnapshot.value
);

// 每次弹窗打开时，用当前账户信息回填表单并打快照
watch(
  () => props.visible,
  val => {
    if (!val) return;
    const info = props.accountInfo;
    if (info) {
      editForm.value = {
        name: info.name,
        // 用 channel_category 回填类型选择（与选项 value 一致），避免回退显示原始值（如 Fund）及提交报错
        ledger_type: info.channel_category || info.ledger_type || "bank",
        default_allocation: info.default_allocation || null,
        notes: info.notes || "",
        portfolio_id: info.portfolio_id || null,
        linked_cash_ledger_id: info.linked_cash_ledger_id || null,
        linked_money_fund_code: info.linked_money_fund_code ?? null,
        auto_purchase_money_fund: info.auto_purchase_money_fund ?? false,
        fee_config: info.fee_config,
        sales_institution_id: info.sales_institution_id ?? null
      };
    }
    editFormSnapshot.value = JSON.stringify(editForm.value);
    saving.value = false;
  }
);

async function handleUpdate() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  saving.value = true;
  try {
    // 编辑时 ledger_type（计算口径键）不可变，绝不要下发；表单里的 ledger_type 字段实际承载
    // 的是渠道分组 channel_category，须映射到 channel_category 下发，否则后端比对真实
    // ledger_type 不等会报「类型不可更改」（支付宝 fund_platform→fund / 证券 securities→stock）。
    const payload: Record<string, any> = { ...editForm.value };
    delete payload.ledger_type;
    payload.channel_category = editForm.value.ledger_type;
    await updateLedger(Number(props.ledgerId), payload);
    ElMessage.success("账户已更新");
    emit("update:visible", false);
    emit("saved");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}
</script>
