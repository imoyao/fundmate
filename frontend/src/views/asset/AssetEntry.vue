<template>
  <div class="asset-entry p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">录入通用资产</h2>
      <p class="text-gray-500 text-sm mt-1">
        记录房产、现金、信用卡、贷款等非交易类资产，完善你的资产负债表
      </p>
    </div>

    <!-- 表单卡片 -->
    <el-card shadow="never" class="entry-card">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
        size="large"
      >
        <el-form-item label="资产名称" prop="name">
          <el-input v-model="form.name" placeholder="如：招商银行活期、阳光花园房产" />
        </el-form-item>

        <el-form-item label="资产大类" prop="major_category">
          <el-select v-model="form.major_category" class="w-full">
            <el-option label="💵 流动资金" value="cash" />
            <el-option label="🏠 固定资产" value="fixed" />
            <el-option label="📈 投资理财" value="investment" />
            <el-option label="🤝 应收款" value="receivable" />
            <el-option label="📉 负债" value="liability" />
            <el-option label="🛡️ 保险" value="insurance" />
          </el-select>
        </el-form-item>

        <el-form-item label="金额" prop="amount">
          <el-input-number
            v-model="form.amount"
            :min="0"
            :precision="2"
            class="w-full"
            placeholder="0.00"
          />
          <p class="text-xs text-gray-400 mt-1">
            负债请填写正数，系统会自动处理
          </p>
        </el-form-item>

        <el-form-item label="配置目标">
          <el-select v-model="form.allocation" class="w-full" clearable placeholder="可选">
            <el-option label="💧 活钱" value="liquid" />
            <el-option label="🛡️ 稳健底仓" value="stable" />
            <el-option label="📈 长期增值" value="longterm" />
            <el-option label="⚡ 高风险博弈" value="speculative" />
            <el-option label="🛟 保险保障" value="security" />
          </el-select>
        </el-form-item>

        <el-form-item label="所属账户">
          <el-select
            v-model="form.account_name"
            class="w-full"
            clearable
            allow-create
            filterable
            placeholder="选择或输入新账户名称"
          >
            <el-option
              v-for="ledger in ledgers"
              :key="ledger.id"
              :label="ledger.name"
              :value="ledger.name"
            />
          </el-select>
          <p class="text-xs text-gray-400 mt-1">
            <IconifyIconOffline icon="ep:info-filled" class="mr-1 align-middle" />
            输入新账户名称后按 Enter 即可创建
          </p>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="form.notes"
            type="textarea"
            :rows="3"
            placeholder="补充说明（可选）"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            确认录入
          </el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { createAsset } from "@/api/assets";
import { getLedgers } from "@/api/ledger";
import type { FormInstance, FormRules } from "element-plus";
import { useRoute } from "vue-router";

const route = useRoute();


defineOptions({ name: "AssetEntry" });

const formRef = ref<FormInstance>();
const submitting = ref(false);
const ledgers = ref<any[]>([]);

const form = reactive({
  name: "",
  major_category: "cash",
  amount: 0,
  allocation: null,
  account_name: "",
  notes: ""
});

const rules: FormRules = {
  name: [{ required: true, message: "请输入资产名称", trigger: "blur" }],
  major_category: [{ required: true, message: "请选择资产大类", trigger: "change" }],
  amount: [{ required: true, message: "请输入金额", trigger: "blur" }]
};

async function fetchLedgers() {
  try {
    const res = await getLedgers();
    ledgers.value = (res as any).data ?? [];
  } catch (e) {
    console.error(e);
  }
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  submitting.value = true;
  try {
    await createAsset({
      major_category: form.major_category,
      name: form.name,
      amount: form.amount,
      allocation: form.allocation || undefined,
      account_name: form.account_name || undefined,
      notes: form.notes || undefined
    });
    ElMessage.success(`已录入资产「${form.name}」`);
    handleReset();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "录入失败");
  } finally {
    submitting.value = false;
  }
}

function handleReset() {
  formRef.value?.resetFields();
  form.name = "";
  form.major_category = "cash";
  form.amount = 0;
  form.allocation = null;
  form.account_name = "";
  form.notes = "";
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
  max-width: 600px;
  margin: 0 auto;
  border-radius: 12px;
}
</style>
