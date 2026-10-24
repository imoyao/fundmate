<script setup lang="ts">
/**
 * 新增账户弹窗（#980 拆分）。
 *
 * 弹窗自己管自己的三件事：表单状态、销售机构候选（只有它用）、创建请求。
 * 建完只把 `{ id, name }` 抛给页面——页面要拿它回填「所属账户」，但不需要知道
 * 弹窗内部怎么取的数。
 *
 * 弹窗的 `:deep(.el-dialog...)` 样式**留在页面**（不随组件搬）：那三条是裸 `:deep`，
 * 编译成 `[data-v-x] .el-dialog`，要求 `.el-dialog` 是带 scopeId 元素的**后代**。
 * 搬进本组件后 el-dialog 就是根元素自己，既不是自己的后代、也匹配不上，
 * 弹窗背景与标题会静默退回 Element Plus 默认样式。
 */
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { createLedger, getSalesInstitutions } from "@/api/ledger";
import type { SalesInstitution } from "@/api/ledger";
import { LEDGER_TYPE_OPTIONS } from "@/constants";

import { filterInstitutions, institutionLabel } from "./assetEntryModel";

const visible = defineModel<boolean>("visible", { required: true });

const emit = defineEmits<{
  (e: "created", ledger: { id: number; name: string }): void;
}>();

const creatingLedger = ref(false);
const newLedgerForm = reactive({
  name: "",
  ledger_type: "bank",
  sales_institution_id: null as number | null
});

/** 基金销售机构候选（AMAC 名录，新增账户可选关联） */
const salesInstitutions = ref<SalesInstitution[]>([]);

/** 销售机构下拉检索关键词（小写），支持汉字/别名/拼音首字母三路匹配（#1081） */
const institutionFilter = ref("");
const filteredInstitutions = computed(() =>
  filterInstitutions(salesInstitutions.value, institutionFilter.value)
);

function filterInstitution(query: string) {
  institutionFilter.value = query.trim().toLowerCase();
}

/** 销售机构候选加载：失败仅记日志，下拉留空（可选字段不阻塞页面） */
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
      sales_institution_id: newLedgerForm.sales_institution_id ?? null
    });
    const newLedger = (res as any).data || res;
    ElMessage.success("账户已创建");
    visible.value = false;
    newLedgerForm.name = "";
    newLedgerForm.sales_institution_id = null;
    emit("created", {
      id: newLedger.id ?? (res as any).id,
      name: newLedger.name || newLedgerForm.name
    });
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    creatingLedger.value = false;
  }
}

onMounted(fetchSalesInstitutions);
</script>

<template>
  <el-dialog v-model="visible" title="新增账户" width="420px" destroy-on-close>
    <el-form :model="newLedgerForm" label-width="80px" size="large">
      <el-form-item label="账户名称" required>
        <el-input
          v-model="newLedgerForm.name"
          placeholder="如：招商银行、华泰证券"
        />
      </el-form-item>
      <el-form-item label="账户类型" required>
        <el-select
          v-model="newLedgerForm.ledger_type"
          class="w-full"
          placeholder="选择账户类型"
        >
          <el-option
            v-for="opt in LEDGER_TYPE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="销售机构">
        <el-select
          v-model="newLedgerForm.sales_institution_id"
          class="w-full"
          clearable
          filterable
          placeholder="可不选，支持汉字/别名/拼音首字母"
          :filter-method="filterInstitution"
        >
          <el-option
            v-for="inst in filteredInstitutions"
            :key="inst.id"
            :label="institutionLabel(inst)"
            :value="inst.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="large" @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="creatingLedger"
        size="large"
        @click="handleCreateLedger"
      >
        确认创建
      </el-button>
    </template>
  </el-dialog>
</template>
