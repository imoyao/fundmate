<script setup lang="ts">
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import AccountFormFields from "./AccountFormFields.vue";
import { createLedger, type SalesInstitution } from "@/api/ledger";

/**
 * 新建账户对话框（#984 ledgers/index.vue 拆分）。
 * 从 index.vue 原样迁移：表单结构、AccountFormFields 接线、创建逻辑不变；
 * 现金账户/组合/销售机构候选由父页面传入（父页面 fetchData 已统一加载）。
 */
const props = defineProps<{
  visible: boolean;
  cashLedgers: any[];
  portfolioList: any[];
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
const createForm = ref({
  name: "",
  ledger_type: "stock",
  notes: "",
  linked_cash_ledger_id: null as number | null,
  portfolio_id: null as number | null,
  fee_config: null as any,
  sales_institution_id: null as number | null
});

// 每次打开重置表单（原 openCreateDialog 的重置语义迁移至此）；
// ledger_type 取外部预置类型（分组入口预填），未指定时维持默认 stock
watch(
  () => props.visible,
  val => {
    if (val) {
      createForm.value = {
        name: "",
        ledger_type: props.initialLedgerType || "stock",
        notes: "",
        linked_cash_ledger_id: null,
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
    await createLedger(createForm.value);
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
