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
 *
 * 2026-11-03 视觉重做：此前本文件手写了主按钮 / 次按钮 / 悬停三套颜色，全部取自
 * `--color-primary`（#7a7fa8 灰紫蓝）——那是旧主色，品牌色早已是 `--brand-700`。
 * 于是「确认录入」是灰紫蓝实底、悬停还带灰紫蓝描边，与全站暖红主按钮两个色系。
 * 现在一律用 `el-button type="primary"` 交给全局主题（`--brand-solid` 三态 + AA 对比度），
 * 本文件不再声明任何按钮颜色。
 */
import { errorMessageOf } from "@/utils/errorMessage";
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import type { FormInstance, FormRules } from "element-plus";

import { createAsset } from "@/api/assets";
import { ALLOCATION_OPTIONS } from "@/constants";
import CardBlock from "@/components/CardBlock/index.vue";

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
  } catch (e) {
    ElMessage.error(errorMessageOf(e) || "录入失败");
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
  <CardBlock>
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="88px"
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
          class="amount-input"
          :controls="false"
          :precision="2"
          :min="0"
          placeholder="0.00"
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
          <el-button size="large" @click="emit('create-ledger')">
            <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
          </el-button>
        </div>
        <p class="form-tip">若没有合适的账户，请先创建</p>
      </el-form-item>

      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="3"
          placeholder="补充说明（可选）"
        />
      </el-form-item>

      <div class="form-actions">
        <el-button size="large" @click="handleReset">重置</el-button>
        <el-button
          size="large"
          type="primary"
          :loading="submitting"
          @click="handleSubmit"
        >
          确认录入
        </el-button>
      </div>
    </el-form>
  </CardBlock>
</template>

<style scoped>
/* 表单项纵向节奏：24px（--space-standard，4px 基数），此前 32px 偏松 */
.entry-form :deep(.el-form-item) {
  margin-bottom: var(--space-standard);
}

/* 标签色走暖色令牌：EP 默认 --el-text-color-regular(#606266) 是冷灰，
   在暖色系统里与正文（--text-secondary）明显不同色温。 */
.entry-form :deep(.el-form-item__label) {
  font-size: var(--text-small);
  color: var(--text-secondary);
}

/* 金额输入框撑满表单宽度。
   不用 Tailwind 的 `w-full`：v4 的 utilities 在 @layer 里，而 EP 的
   `.el-input-number{width:150px}` 是无层样式——无层优先于有层，`w-full` 会静默失效。
   这里写法带 scoped 属性选择器 (0,2,0)，稳过 EP 的 (0,1,0)。 */
.entry-form .amount-input {
  width: 100%;
}

/* 金额右对齐（唯一保留的输入类 :deep，纯几何，且只作用于金额这一项）：
   钱是按小数点对齐读的，左对齐的数字串在表单里最难核对右侧位数。
   选择器必须挂 `.amount-input` 这一层——直接对表单根下的 inner 生效，
   会把「资产名称」也一起右对齐。 */
.entry-form .amount-input :deep(.el-input__inner) {
  text-align: right;
}

.form-tip {
  margin-top: 6px;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

/* 账户选择行：下拉框吃掉剩余宽度，新增按钮保持自身宽度 */
.account-select-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  width: 100%;
}

/* 操作区：右对齐（与「手动记账」页 ManualActionBar、各录入弹窗一致），
   主操作在右、次操作在左，符合从左到右的阅读与视线落点。 */
.form-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
  padding-top: var(--space-2);
}
</style>
