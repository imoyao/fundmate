<script setup lang="ts">
/**
 * 录入通用资产的表单（#980 拆分）。
 *
 * 表单自己持有 `form`、校验规则、提交与重置——页面只喂「账户列表」和「URL 解析出的初值」。
 * 这样切分是因为这三件事互为一体：校验规则引用 `form` 的字段、重置要逐字段清空、
 * 提交要把 `form` 翻成 payload，任何一件搬走都得把 `form` 也一起搬。
 *
 * 「新增账户」按钮不在这里开弹窗：弹窗建完账户要写回本表单的 `ledger_id` /
 * `account_name`，而弹窗是页面的兄弟节点。所以这里只抛 `create-ledger`，
 * 由页面转一道后把 `pickedLedger` 递回来。
 */
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import type { FormInstance, FormRules } from "element-plus";

import { createAsset } from "@/api/assets";
import { ALLOCATION_OPTIONS } from "@/constants";

import AssetCategoryFields from "./AssetCategoryFields.vue";
import { buildAssetPayload, createEmptyForm } from "./assetEntryModel";

const props = defineProps<{
  ledgers: any[];
  /** URL 解析出的初值（大类 + 细分），只在挂载时用一次 */
  initial: { major_category: string; minor_category: string | null };
  /** 弹窗新建的账户：非空时回填到「所属账户」 */
  pickedLedger: { id: number; name: string } | null;
}>();

const emit = defineEmits<{ (e: "create-ledger"): void }>();

const formRef = ref<FormInstance>();
const submitting = ref(false);

const form = reactive({
  ...createEmptyForm(),
  major_category: props.initial.major_category,
  minor_category: props.initial.minor_category
});

watch(
  () => props.pickedLedger,
  ledger => {
    if (!ledger) return;
    form.ledger_id = ledger.id;
    form.account_name = ledger.name;
  }
);

// 选择账户后自动填充 account_name（快照用）
function onLedgerSelected(ledgerId: number | undefined) {
  if (ledgerId == null) return;
  const ledger = props.ledgers.find(l => l.id === ledgerId);
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
    await createAsset(buildAssetPayload(form));
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
  Object.assign(form, createEmptyForm());
}
</script>

<template>
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

      <!-- 大类 + 两个子类选择器（三者联动，收在同一个子组件里） -->
      <AssetCategoryFields
        v-model:major-category="form.major_category"
        v-model:minor-category="form.minor_category"
      />

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

      <el-form-item v-if="form.major_category !== 'liability'" label="配置目标">
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

      <el-form-item label="所属账户" prop="ledger_id">
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
            @click="emit('create-ledger')"
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
</template>

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
  font-size: var(--text-body);
  line-height: 44px;
  color: var(--text-primary);
}

/* 优化必填星号样式：增加间距，垂直居中 */
.entry-form :deep(.el-form-item__label-wrap .el-form-item__required) {
  margin-right: 4px;
  vertical-align: middle;
  color: var(--color-danger);
}

/* 本表单的输入框圆角是 8px（比基线 --radius-sm 6px 更圆，与卡片区一致）：
   走 #1772 输入基线的圆角令牌，一次性覆盖单行 / 文本域 / 下拉三种控件。
   —— 原先写在 `.el-input__inner` 上的 `border-radius: 8px` 其实是死代码
   （EP 的 .el-input__inner 是 `border:none; background:none`，圆角画不出来），
   真正一直生效的只有文本域那条，单行输入其实一直是 4px。 */
.entry-form {
  --input-radius: 8px;
}

/* 统一输入框字号与内边距（几何差异，走 :deep 是本 issue 允许的例外之一） */
.entry-form :deep(.el-input__inner) {
  padding-right: 14px;
  padding-left: 14px;
  font-size: var(--text-body);
  color: var(--text-primary);
  background-color: var(--bg-card);
  border-color: var(--border-default);
}

.entry-form :deep(.el-textarea__inner) {
  padding: 12px 14px;
  font-size: var(--text-body);
  color: var(--text-primary);
  resize: vertical;
  background-color: var(--bg-card);
  border-color: var(--border-default);
}

/* 金额输入框全面优化 */
.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input-number__decrease),
.amount-input :deep(.el-input-number__increase) {
  width: 44px;
  font-size: var(--text-num-strong);
  color: var(--text-secondary);
  background-color: var(--bg-muted);
  border: none;
  border-radius: 8px;
  transition: all 0.2s;
}

.amount-input :deep(.el-input-number__decrease:hover),
.amount-input :deep(.el-input-number__increase:hover) {
  color: var(--color-primary-ink);
  background-color: var(--bg-hover);
}

.amount-input :deep(.el-input__inner) {
  padding-right: 16px;
  text-align: right;
}

/* 提示文字样式优化：提升可读性 */
.form-tip {
  padding-left: 2px;
  margin-top: 6px;
  font-size: var(--text-label);
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
  color: var(--color-primary-ink);
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
  font-size: var(--text-body);
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
  font-size: var(--text-body);
  color: var(--text-primary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: all 0.2s;
}

.reset-btn:hover {
  color: var(--color-primary-ink);
  background-color: var(--color-primary-20);
  border-color: var(--color-primary);
}
</style>
