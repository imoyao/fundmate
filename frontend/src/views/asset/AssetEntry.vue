<template>
  <div class="asset-entry p-4 md:p-6 min-h-full" :style="{ backgroundColor: 'var(--bg-page)' }">
    <div class="mb-6">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">录入通用资产</h2>
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
          <el-input v-model="form.name" placeholder="如：招商银行活期、阳光花园房产" />
        </el-form-item>

        <el-form-item label="资产大类" prop="major_category">
          <el-select v-model="form.major_category" class="w-full">
            <el-option label="流动资金" value="cash" />
            <el-option label="固定资产" value="fixed" />
            <el-option label="投资理财" value="investment" />
            <el-option label="应收款" value="receivable" />
            <el-option label="负债" value="liability" />
            <el-option label="保险" value="insurance" />
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

        <el-form-item label="配置目标" v-if="form.major_category !== 'liability'">
          <el-select v-model="form.allocation" class="w-full" clearable placeholder="请选择配置目标">
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
              @change="onLedgerSelected"
              class="flex-1"
              clearable
              filterable
              placeholder="选择已有账户"
            >
              <el-option
                v-for="ledger in ledgers"
                :key="ledger.id"
                :label="ledger.name"
                :value="ledger.id"
              />
            </el-select>
            <el-button class="add-ledger-btn" size="large" @click="showCreateLedgerDialog = true">
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
            <el-button type="primary" :loading="submitting" @click="handleSubmit" class="submit-btn">
              确认录入
            </el-button>
            <el-button @click="handleReset" class="reset-btn">重置</el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 新增账户弹窗 -->
    <el-dialog v-model="showCreateLedgerDialog" title="新增账户" width="420px" destroy-on-close>
      <el-form :model="newLedgerForm" label-width="80px" size="large">
        <el-form-item label="账户名称" required>
          <el-input v-model="newLedgerForm.name" placeholder="如：招商银行、华泰证券" />
        </el-form-item>
        <el-form-item label="账户类型" required>
          <el-select v-model="newLedgerForm.ledger_type" class="w-full" placeholder="选择账户类型">
            <el-option
              v-for="opt in LEDGER_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateLedgerDialog = false" size="large">取消</el-button>
        <el-button type="primary" :loading="creatingLedger" @click="handleCreateLedger" size="large">
          确认创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { createAsset } from "@/api/assets";
import { getLedgers, createLedger } from "@/api/ledger";
import type { FormInstance, FormRules } from "element-plus";
import { useRoute } from "vue-router";
import { ALLOCATION_OPTIONS, LEDGER_TYPE_OPTIONS  } from '@/constants'

const route = useRoute();

defineOptions({ name: "AssetEntry" });

const formRef = ref<FormInstance>();
const submitting = ref(false);
const ledgers = ref<any[]>([]);

// 新增账户相关
const showCreateLedgerDialog = ref(false);
const creatingLedger = ref(false);
const newLedgerForm = reactive({ name: "", ledger_type: "bank" });

// 表单数据
const form = reactive({
  name: "",
  major_category: "cash",
  amount: 0,
  allocation: null,
  ledger_id: null as number | null,   // 新增
  account_name: "",                    // 保留为后端回填的快照
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
  major_category: [{ required: true, message: "请选择资产大类", trigger: "change" }],
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
  ledger_id: [{ required: true, message: "请选择所属账户", trigger: "change" }]  // 改为 ledger_id
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
      ledger_id: form.ledger_id,           // 关键：传递 ledger_id
      account_name: form.account_name || undefined,
      notes: form.notes || undefined
    };
    if (form.major_category !== 'liability' && form.allocation) {
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

async function handleCreateLedger() {
  if (!newLedgerForm.name.trim()) {
    ElMessage.warning("请输入账户名称");
    return;
  }
  creatingLedger.value = true;
  try {
    const res = await createLedger({ name: newLedgerForm.name, ledger_type: newLedgerForm.ledger_type, currency: "CNY" });
    const newLedger = (res as any).data || res;
    ElMessage.success("账户已创建");
    showCreateLedgerDialog.value = false;
    newLedgerForm.name = "";
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
  const category = route.query.category as string;
  if (category) {
    form.major_category = category;
  }
});
</script>

<style scoped>
.entry-card {
  max-width: 700px;
  margin: 0 auto;
  border-radius: 16px;
  padding: 32px 40px;
  background-color: var(--bg-card);
}

/* 表单项垂直间距增大，提升呼吸感 */
.entry-form :deep(.el-form-item) {
  margin-bottom: 32px;
}

/* 标签与输入框完美居中对齐（匹配Element Plus large尺寸44px高度） */
.entry-form :deep(.el-form-item__label) {
  line-height: 44px;
  font-size: 15px;
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
  padding-left: 14px;
  padding-right: 14px;
  border-radius: 8px;
  font-size: 15px;
  border-color: var(--border-default);
  background-color: var(--bg-card);
  color: var(--text-primary);
}

.entry-form :deep(.el-textarea__inner) {
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 15px;
  border-color: var(--border-default);
  background-color: var(--bg-card);
  color: var(--text-primary);
  resize: vertical;
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
  border-radius: 8px;
  background-color: var(--bg-muted);
  border: none;
  font-size: 18px;
  color: var(--text-secondary);
  transition: all 0.2s;
}
.amount-input :deep(.el-input-number__decrease:hover),
.amount-input :deep(.el-input-number__increase:hover) {
  background-color: var(--bg-hover);
  color: var(--color-primary);
}
.amount-input :deep(.el-input__inner) {
  text-align: right;
  padding-right: 16px;
  border-radius: 8px;
}

/* 提示文字样式优化：提升可读性 */
.form-tip {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 6px;
  line-height: 1.5;
  padding-left: 2px;
}

/* 账户选择行：确保按钮与下拉框高度一致 */
.account-select-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* 新增账户按钮：边框式次要按钮，明确区分输入项与操作项 */
.add-ledger-btn {
  white-space: nowrap;
  padding: 0 20px;
  border-radius: 8px;
  border: 1px solid var(--border-default);
  background-color: var(--bg-card);
  color: var(--text-primary);
  transition: all 0.2s;
}
.add-ledger-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background-color: var(--color-primary-20);
}

/* 可选项目：标签弱化+明确标注，降低认知负担 */
.optional-item :deep(.el-form-item__label) {
  color: var(--text-secondary);
  font-weight: 400;
}

/* 操作按钮区域：统一尺寸，平衡视觉 */
.form-actions {
  display: flex;
  gap: 16px;
  padding-top: 8px;
}

.submit-btn {
  padding: 12px 40px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 500;
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}
.submit-btn:hover {
  background-color: var(--color-primary);
  opacity: 0.9;
}

.reset-btn {
  padding: 12px 40px;
  border-radius: 8px;
  font-size: 15px;
  border: 1px solid var(--border-default);
  background-color: var(--bg-card);
  color: var(--text-primary);
  transition: all 0.2s;
}
.reset-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background-color: var(--color-primary-20);
}

/* 弹窗样式优化 */
:deep(.el-dialog) {
  border-radius: 16px;
  background-color: var(--bg-card);
}
:deep(.el-dialog__title) {
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 600;
}
:deep(.el-dialog__body) {
  padding: 24px 32px;
}
</style>
