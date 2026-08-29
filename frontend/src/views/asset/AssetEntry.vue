<template>
  <div
    class="asset-entry p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-6">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        录入通用资产
      </h2>
      <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
        记录房产、现金、信用卡、贷款等非交易类资产，完善你的资产负债表
      </p>
    </div>

    <el-card shadow="never" class="entry-card">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="110px"
        size="large"
        class="entry-form"
      >
        <el-form-item label="资产名称" prop="name">
          <el-input
            v-model="form.name"
            placeholder="如：招商银行活期、阳光花园房产"
          />
        </el-form-item>

        <el-form-item label="资产大类" prop="major_category">
          <el-select v-model="form.major_category" class="w-full">
            <el-option
              v-for="(label, key) in MAJOR_CATEGORY_LABELS"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="金额" prop="amount">
          <el-input-number
            v-model="form.amount"
            :precision="2"
            class="amount-input"
            placeholder="0.00"
            :step="1"
            controls-position="right"
          />
          <p class="form-tip">负债请填写正数，系统会自动处理为负债</p>
        </el-form-item>

        <el-form-item
          v-if="form.major_category !== 'liability'"
          label="配置目标"
        >
          <el-select
            v-model="form.allocation"
            class="w-full"
            clearable
            placeholder="请选择配置目标"
          >
            <el-option
              v-for="opt in ALLOCATION_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="所属账户" prop="account_name">
          <div class="account-select-row">
            <el-select
              v-model="form.ledger_id"
              class="flex-1"
              clearable
              filterable
              placeholder="选择已有账户"
              @change="onLedgerSelected"
            >
              <el-option
                v-for="ledger in ledgers"
                :key="ledger.id"
                :label="ledger.name"
                :value="ledger.id"
              />
            </el-select>
            <el-button
              class="add-ledger-btn"
              size="large"
              @click="showCreateLedgerDialog = true"
            >
              <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
            </el-button>
          </div>
          <p class="form-tip">若没有合适的账户，请先创建</p>
        </el-form-item>

        <el-form-item label="备注 (可选)" class="optional-item">
          <el-input
            v-model="form.notes"
            type="textarea"
            :rows="3"
            placeholder="补充说明（可选）"
          />
        </el-form-item>

        <el-form-item>
          <div class="form-actions">
            <el-button
              type="primary"
              :loading="submitting"
              class="submit-btn"
              @click="handleSubmit"
            >
              确认录入
            </el-button>
            <el-button class="reset-btn" @click="handleReset">重置</el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 新增账户弹窗 -->
    <el-dialog
      v-model="showCreateLedgerDialog"
      title="新增账户"
      width="420px"
      destroy-on-close
    >
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
        <el-button size="large" @click="showCreateLedgerDialog = false"
          >取消</el-button
        >
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { createAsset } from "@/api/assets";
import {
  getLedgers,
  createLedger,
  getSalesInstitutions,
  type SalesInstitution
} from "@/api/ledger";
import type { FormInstance, FormRules } from "element-plus";
import { useRoute } from "vue-router";
import {
  ALLOCATION_OPTIONS,
  LEDGER_TYPE_OPTIONS,
  MAJOR_CATEGORY_LABELS
} from "@/constants";

const route = useRoute();

defineOptions({ name: "AssetEntry" });

const formRef = ref<FormInstance>();
const submitting = ref(false);
const ledgers = ref<any[]>([]);

// 新增账户相关
const showCreateLedgerDialog = ref(false);
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
const filteredInstitutions = computed(() => {
  const kw = institutionFilter.value;
  if (!kw) return salesInstitutions.value;
  return salesInstitutions.value.filter(
    inst =>
      inst.org_name.toLowerCase().includes(kw) ||
      (inst.display_name ?? "").toLowerCase().includes(kw) ||
      (inst.pinyin_short ?? "").toLowerCase().includes(kw)
  );
});
function filterInstitution(query: string) {
  institutionFilter.value = query.trim().toLowerCase();
}

// 表单数据
const form = reactive({
  name: "",
  major_category: "cash",
  amount: 0,
  allocation: null,
  ledger_id: null as number | null, // 新增
  account_name: "", // 保留为后端回填的快照
  notes: ""
});

// 选择账户后自动填充 account_name（快照用）
function onLedgerSelected(ledgerId: number | undefined) {
  if (ledgerId == null) return;
  const ledger = ledgers.value.find(l => l.id === ledgerId);
  if (ledger) form.account_name = ledger.name;
}

// 校验规则修改
const rules: FormRules = {
  name: [{ required: true, message: "请输入资产名称", trigger: "blur" }],
  major_category: [
    { required: true, message: "请选择资产大类", trigger: "change" }
  ],
  amount: [
    { required: true, message: "请输入金额", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value <= 0) {
          callback(new Error("金额必须大于0"));
        } else {
          callback();
        }
      },
      trigger: "blur"
    }
  ],
  ledger_id: [{ required: true, message: "请选择所属账户", trigger: "change" }] // 改为 ledger_id
};

// 提交逻辑
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  submitting.value = true;
  try {
    const payload: any = {
      major_category: form.major_category,
      name: form.name,
      amount: form.amount,
      ledger_id: form.ledger_id, // 关键：传递 ledger_id
      account_name: form.account_name || undefined,
      notes: form.notes || undefined
    };
    if (form.major_category !== "liability" && form.allocation) {
      payload.allocation = form.allocation;
    }
    await createAsset(payload);
    ElMessage.success(`已录入资产「${form.name}」`);
    handleReset();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "录入失败");
  } finally {
    submitting.value = false;
  }
}

// 重置时也要清空 ledger_id
function handleReset() {
  formRef.value?.resetFields();
  form.name = "";
  form.major_category = "cash";
  form.amount = 0;
  form.allocation = null;
  form.ledger_id = null;
  form.account_name = "";
  form.notes = "";
}

async function fetchLedgers() {
  try {
    const res = await getLedgers();
    ledgers.value = (res as any).data ?? [];
  } catch (e) {
    console.error(e);
  }
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

/** 下拉展示：优先「权威全称（常用别名）」，无别名则仅全称 */
function institutionLabel(inst: SalesInstitution): string {
  return inst.display_name
    ? `${inst.org_name}（${inst.display_name}）`
    : inst.org_name;
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
    showCreateLedgerDialog.value = false;
    newLedgerForm.name = "";
    newLedgerForm.sales_institution_id = null;
    await fetchLedgers();
    form.ledger_id = newLedger.id || (res as any).id;
    form.account_name = newLedger.name || newLedgerForm.name;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    creatingLedger.value = false;
  }
}

onMounted(() => {
  fetchLedgers();
  fetchSalesInstitutions();
  const category = route.query.category as string;
  if (category) {
    form.major_category = category;
  }
});
</script>

<style scoped>
.entry-card {
  max-width: 700px;
  padding: 32px 40px;
  margin: 0 auto;
  background-color: var(--bg-card);
  border-radius: 16px;
}

/* 表单项垂直间距增大，提升呼吸感 */
.entry-form :deep(.el-form-item) {
  margin-bottom: 32px;
}

/* 标签与输入框完美居中对齐（匹配Element Plus large尺寸44px高度） */
.entry-form :deep(.el-form-item__label) {
  font-size: 15px;
  line-height: 44px;
  color: var(--text-primary);
}

/* 优化必填星号样式：增加间距，垂直居中 */
.entry-form :deep(.el-form-item__label-wrap .el-form-item__required) {
  margin-right: 4px;
  vertical-align: middle;
  color: var(--color-danger);
}

/* 统一输入框圆角和内边距 */
.entry-form :deep(.el-input__inner) {
  padding-right: 14px;
  padding-left: 14px;
  font-size: 15px;
  color: var(--text-primary);
  background-color: var(--bg-card);
  border-color: var(--border-default);
  border-radius: 8px;
}

.entry-form :deep(.el-textarea__inner) {
  padding: 12px 14px;
  font-size: 15px;
  color: var(--text-primary);
  resize: vertical;
  background-color: var(--bg-card);
  border-color: var(--border-default);
  border-radius: 8px;
}

.entry-form :deep(.el-select .el-input__inner) {
  padding-right: 36px;
}

/* 输入框聚焦状态 */
.entry-form :deep(.el-input__inner:focus) {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-20);
}

/* 金额输入框全面优化 */
.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input-number__decrease),
.amount-input :deep(.el-input-number__increase) {
  width: 44px;
  font-size: 18px;
  color: var(--text-secondary);
  background-color: var(--bg-muted);
  border: none;
  border-radius: 8px;
  transition: all 0.2s;
}

.amount-input :deep(.el-input-number__decrease:hover),
.amount-input :deep(.el-input-number__increase:hover) {
  color: var(--color-primary);
  background-color: var(--bg-hover);
}

.amount-input :deep(.el-input__inner) {
  padding-right: 16px;
  text-align: right;
  border-radius: 8px;
}

/* 提示文字样式优化：提升可读性 */
.form-tip {
  padding-left: 2px;
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}

/* 账户选择行：确保按钮与下拉框高度一致 */
.account-select-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* 新增账户按钮：边框式次要按钮，明确区分输入项与操作项 */
.add-ledger-btn {
  padding: 0 20px;
  color: var(--text-primary);
  white-space: nowrap;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: all 0.2s;
}

.add-ledger-btn:hover {
  color: var(--color-primary);
  background-color: var(--color-primary-20);
  border-color: var(--color-primary);
}

/* 可选项目：标签弱化+明确标注，降低认知负担 */
.optional-item :deep(.el-form-item__label) {
  font-weight: 400;
  color: var(--text-secondary);
}

/* 操作按钮区域：统一尺寸，平衡视觉 */
.form-actions {
  display: flex;
  gap: 16px;
  padding-top: 8px;
}

.submit-btn {
  padding: 12px 40px;
  font-size: 15px;
  font-weight: 500;
  background-color: var(--color-primary);
  border-color: var(--color-primary);
  border-radius: 8px;
}

.submit-btn:hover {
  background-color: var(--color-primary);
  opacity: 0.9;
}

.reset-btn {
  padding: 12px 40px;
  font-size: 15px;
  color: var(--text-primary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: all 0.2s;
}

.reset-btn:hover {
  color: var(--color-primary);
  background-color: var(--color-primary-20);
  border-color: var(--color-primary);
}

/* 弹窗样式优化 */
:deep(.el-dialog) {
  background-color: var(--bg-card);
  border-radius: 16px;
}

:deep(.el-dialog__title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.el-dialog__body) {
  padding: 24px 32px;
}
</style>
