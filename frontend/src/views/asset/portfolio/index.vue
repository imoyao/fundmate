<!-- portfolio/index.vue -->
<template>
  <div
    class="portfolio-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          投资组合
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
          管理你的投资策略组合，关联账户进行收益分析
        </p>
      </div>
      <el-button type="primary" @click="openCreateDialog">
        <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新建组合
      </el-button>
    </div>

    <!-- 加载状态 -->
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <p>加载中...</p>
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="portfolios.length === 0"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <IconifyIconOffline
        icon="ep:collection"
        class="text-5xl mb-3 opacity-30"
      />
      <p class="text-lg">暂无投资组合，点击上方按钮创建</p>
    </div>

    <!-- 卡片列表 -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <div
        v-for="item in portfolios"
        :key="item.id"
        class="portfolio-card"
        @click="$router.push(`/asset/portfolios/${item.id}`)"
      >
        <div class="flex items-center justify-between mb-3">
          <h3
            class="font-semibold text-base"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ item.name }}
          </h3>
          <el-popconfirm
            title="确定删除此组合？关联账户将自动解绑。"
            @confirm="handleDelete(item.id)"
            @click.stop
          >
            <template #reference>
              <el-button type="danger" size="small" circle @click.stop>
                <IconifyIconOffline icon="ep:delete" />
              </el-button>
            </template>
          </el-popconfirm>
        </div>
        <div class="flex flex-col gap-2">
          <div class="flex items-center gap-2">
            <span
              class="text-xs px-2 py-0.5 rounded-full"
              :style="{
                backgroundColor: 'var(--bg-page)',
                color: 'var(--text-secondary)'
              }"
            >
              {{ item.purpose || "未设定目的" }}
            </span>
          </div>
          <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
            创建于 {{ item.created_at?.slice(0, 10) }}
          </p>
        </div>
      </div>
    </div>

    <!-- 仅保留创建对话框 -->
    <el-dialog
      v-model="dialogVisible"
      title="新建组合"
      width="500px"
      destroy-on-close
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="组合名称" required>
          <el-input v-model="form.name" placeholder="如：养老计划" />
        </el-form-item>
        <el-form-item label="投资目的">
          <el-input v-model="form.purpose" placeholder="如：长期增值" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="可选"
          />
        </el-form-item>
        <el-form-item label="目标收益率">
          <el-input-number
            v-model="form.target_return"
            :min="0"
            :max="100"
            :precision="2"
            controls-position="right"
            class="w-full"
            placeholder="年化目标（%）"
          />
        </el-form-item>
        <el-form-item label="目标金额">
          <el-input-number
            v-model="form.target_amount"
            :min="0"
            :precision="2"
            controls-position="right"
            class="w-full"
            placeholder="目标金额"
          />
        </el-form-item>
        <el-form-item label="目标日期">
          <el-date-picker
            v-model="form.target_date"
            type="date"
            placeholder="选择日期"
            class="w-full"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="基准指数">
          <el-select
            v-model="form.benchmark"
            class="w-full"
            clearable
            filterable
            allow-create
          >
            <el-option label="沪深300" value="CSI300" />
            <el-option label="中证500" value="CSI500" />
            <el-option label="标普500" value="SPX" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave"
          >创建</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getPortfolios,
  createPortfolio,
  deletePortfolio,
  type PortfolioItem
} from "@/api/portfolio";

defineOptions({ name: "PortfolioList" });

const portfolios = ref<PortfolioItem[]>([]);
const loading = ref(true);
const dialogVisible = ref(false);
const saving = ref(false);

const defaultForm = {
  name: "",
  purpose: "",
  description: "",
  target_return: undefined as number | undefined,
  target_amount: undefined as number | undefined,
  target_date: "",
  benchmark: ""
};
const form = ref({ ...defaultForm });

function openCreateDialog() {
  form.value = { ...defaultForm };
  dialogVisible.value = true;
}

async function handleSave() {
  if (!form.value.name.trim()) {
    ElMessage.warning("请输入组合名称");
    return;
  }
  saving.value = true;
  try {
    await createPortfolio({
      name: form.value.name,
      purpose: form.value.purpose || undefined,
      description: form.value.description || undefined,
      target_return: form.value.target_return,
      target_amount: form.value.target_amount,
      target_date: form.value.target_date || undefined,
      benchmark: form.value.benchmark || undefined
    });
    ElMessage.success("组合已创建");
    dialogVisible.value = false;
    await fetchList();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    saving.value = false;
  }
}

async function handleDelete(id: number) {
  try {
    await deletePortfolio(id);
    ElMessage.success("组合已删除");
    await fetchList();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  }
}

async function fetchList() {
  loading.value = true;
  try {
    const res = await getPortfolios();
    // 兼容不同响应格式
    portfolios.value = (res as any)?.data?.data ?? (res as any)?.data ?? [];
  } catch (e) {
    ElMessage.error("加载组合列表失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  fetchList();
});
</script>

<style scoped>
.portfolio-page {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.portfolio-card {
  padding: 20px;
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  transition: all 0.2s;
}

.portfolio-card:hover {
  box-shadow: 0 4px 16px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
}
</style>
