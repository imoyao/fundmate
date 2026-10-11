<template>
  <el-dialog
    :model-value="visible"
    title="编辑账户"
    width="420px"
    destroy-on-close
    :before-close="onBeforeClose"
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
      <!-- 取消走 requestClose：before-close 只拦关闭按钮 / ESC / 点遮罩，
           程序化 close 走不到它（#1835 同坑，CreateAccountDialog 同形） -->
      <el-button @click="requestClose(() => emit('update:visible', false))"
        >取消</el-button
      >
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!isDirty"
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
import {
  useUnsavedChangesGuard,
  useDialogForm
} from "@/composables/useUnsavedChangesGuard";
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

function emptyEditForm(): EditAccountForm {
  return {
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
  };
}

const editForm = ref<EditAccountForm>(emptyEditForm());
const saving = ref(false);

// 脏基线与「打开时回填」绑在一起（#1896）。
//
// 本文件此前自己写了一份 `editFormSnapshot` + `JSON.stringify` 比较，但**只用来禁用保存按钮**
// ——没有任何人读它，于是「改了费率配置点关闭按钮 / ESC / 点遮罩」全程静默丢弃。
// 而 `AccountFormFields` 的三个宿主里 `CreateAccountDialog` 早就接了守卫（#1892），
// 只有它漏了。现在收敛到共享 helper，顺带消除这份重复实现。
const { isDirty, fillOnOpen, markSaved } = useDialogForm(
  editForm,
  emptyEditForm
);

// 每次弹窗打开时，用当前账户信息回填表单；关闭时复位为空表单。
// 两件事必须同一个入口（#1880）：只做一半会复现「保存后仍弹未保存修改」的变种。
watch(
  () => props.visible,
  val => {
    const info = props.accountInfo;
    fillOnOpen(val, () =>
      info
        ? {
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
          }
        : emptyEditForm()
    );
    saving.value = false;
  }
);

// 未保存离开保护（#1896）。守卫内部自己注册 onBeforeRouteLeave（路由离开一路，
// 调用方无需接线），但关闭按钮 / ESC / 点遮罩（onBeforeClose，挂 :before-close）
// 与底部「取消」（requestClose，程序化 close 走不到 before-close）这两路必须
// 由宿主显式接上——PR #1898 首版只调用不解构，核心诉求「点关闭要弹确认」未达成。
const { onBeforeClose, requestClose } = useUnsavedChangesGuard(
  () => isDirty.value,
  {
    message: "账户信息已改动，确定放弃吗？"
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
    // 保存成功后把当前值记为新基线（#1896）：否则 isDirty 仍为 true，
    // 保存后关闭弹窗再离开页面仍会被问「账户信息已改动，确定放弃吗？」——
    // 问的是一件已经做完的事。
    markSaved();
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
