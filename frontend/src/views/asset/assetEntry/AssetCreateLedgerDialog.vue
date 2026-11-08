<script setup lang="ts">
/**
 * 新增账户弹窗（资产录入页）。
 *
 * 2026-11-08（#2980）：原先这里**自己手写**了一套表单——只有「名称 / 类型 / 销售机构」
 * 三个字段，且复制了一份机构检索函数（`assetEntryModel.filterInstitutions`）。结果是
 * 同一张账户表在三个入口长出三套字段集（账本页 6 项 / 导入向导 5 项 / 这里 3 项），
 * 用户在资产录入页新建的账户永远缺归属成员与关联信息，且没有任何提示解释差异。
 *
 * 现在改为复用 `AccountFormFields` —— 字段集、机构检索、类型联动只有一处实现，
 * 三个入口天然不漂移。`advanced-collapsed` 让「组合 / 费率」默认收起，保持本入口
 * 的轻量感（它建的只是账户，主体仍是随后录入的资产）。
 *
 * 弹窗自己管三件事：表单状态、销售机构候选、创建请求。建完只把 `{ id, name }`
 * 抛给页面——页面要拿它回填「所属账户」，不需要知道弹窗内部怎么取的数。
 */
import { errorMessageOf } from "@/utils/errorMessage";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { createLedger, getSalesInstitutions } from "@/api/ledger";
import type { LedgerItem, SalesInstitution } from "@/api/ledger";
import AccountFormFields from "@/views/asset/ledgers/components/AccountFormFields.vue";
import OwnerMemberSelect from "@/views/asset/ledgers/components/OwnerMemberSelect.vue";

const visible = defineModel<boolean>("visible", { required: true });

const props = withDefaults(
  defineProps<{
    /** 全量账户，用于派生「可关联的现金账户」候选（与账本页同口径） */
    ledgers?: LedgerItem[];
  }>(),
  { ledgers: () => [] }
);

const emit = defineEmits<{
  (e: "created", ledger: { id: number; name: string }): void;
}>();

const creatingLedger = ref(false);

/** 表单字段与 `CreateAccountDialog` / 导入向导同源（字段集一致，#2980） */
function emptyForm() {
  return {
    name: "",
    ledger_type: "bank",
    linked_cash_ledger_id: null as number | null,
    linked_money_fund_code: null as string | null,
    auto_purchase_money_fund: false,
    portfolio_id: null as number | null,
    fee_config: null as Record<string, unknown> | null,
    sales_institution_id: null as number | null,
    owner_member_id: null as number | null
  };
}

const newLedgerForm = reactive(emptyForm());

/** 基金销售机构候选（AMAC 名录） */
const salesInstitutions = ref<SalesInstitution[]>([]);

/** 可关联的现金账户：与 `useLedgerList` 同口径（计算口径为 bank 的账户） */
const cashLedgers = computed(() =>
  props.ledgers.filter(l => l.ledger_type === "bank")
);

/** 候选加载失败仅记日志：可选字段不阻塞建账户 */
async function fetchSalesInstitutions() {
  try {
    const res = await getSalesInstitutions();
    salesInstitutions.value = res?.data ?? [];
  } catch (e) {
    console.error(e);
  }
}

async function handleCreateLedger() {
  if (!newLedgerForm.name.trim()) {
    ElMessage.warning("请输入账户名称");
    return;
  }
  creatingLedger.value = true;
  try {
    const res = await createLedger({
      name: newLedgerForm.name,
      // 表单 ledger_type 字段承载的是「渠道分组」值（bank/securities/fund_platform/...，
      // 见 LEDGER_TYPE_OPTIONS），必须作为 channel_category 下发，后端据其派生真实
      // ledger_type；若误作 ledger_type 下发会写入伪类型（如 fund_platform 而非 fund）。
      channel_category: newLedgerForm.ledger_type,
      currency: "CNY",
      sales_institution_id: newLedgerForm.sales_institution_id ?? null,
      linked_cash_ledger_id: newLedgerForm.linked_cash_ledger_id ?? null,
      linked_money_fund_code: newLedgerForm.linked_money_fund_code ?? null,
      auto_purchase_money_fund: newLedgerForm.auto_purchase_money_fund,
      portfolio_id: newLedgerForm.portfolio_id ?? null,
      fee_config: newLedgerForm.fee_config,
      owner_member_id: newLedgerForm.owner_member_id ?? null
    });
    // 兼容后端裸对象与信封两种形态，断言只发生在这一处边界
    const legacy = res as unknown as { id?: number; name?: string };
    const newLedger = res?.data ?? legacy;
    ElMessage.success("账户已创建");
    visible.value = false;
    Object.assign(newLedgerForm, emptyForm());
    emit("created", {
      id: (newLedger.id ?? legacy.id) as number,
      name: newLedger.name || newLedgerForm.name
    });
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "创建失败");
  } finally {
    creatingLedger.value = false;
  }
}

onMounted(fetchSalesInstitutions);
</script>

<template>
  <el-dialog
    v-model="visible"
    title="新增账户"
    :width="'var(--dialog-width-form)'"
    class="form-dialog"
    align-center
    destroy-on-close
  >
    <el-form :model="newLedgerForm" label-width="100px">
      <el-form-item label="账户名称" required>
        <el-input
          v-model="newLedgerForm.name"
          placeholder="如：招商银行、华泰证券"
          maxlength="30"
        />
      </el-form-item>
      <AccountFormFields
        v-model:channel-category="newLedgerForm.ledger_type"
        v-model:linked-cash-id="newLedgerForm.linked_cash_ledger_id"
        v-model:linked-money-fund-code="newLedgerForm.linked_money_fund_code"
        v-model:auto-purchase-money-fund="
          newLedgerForm.auto_purchase_money_fund
        "
        v-model:portfolio-id="newLedgerForm.portfolio_id"
        v-model:fee-config="newLedgerForm.fee_config"
        v-model:sales-institution-id="newLedgerForm.sales_institution_id"
        :cash-ledgers="cashLedgers"
        :portfolio-list="[]"
        :sales-institutions="salesInstitutions"
        :advanced-collapsed="true"
      />
      <OwnerMemberSelect v-model="newLedgerForm.owner_member_id" />
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="creatingLedger"
        :disabled="!newLedgerForm.name.trim()"
        @click="handleCreateLedger"
      >
        确认创建
      </el-button>
    </template>
  </el-dialog>
</template>
