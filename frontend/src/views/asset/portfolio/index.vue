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
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
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
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <p>加载中...</p>
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="portfolios.length === 0"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <IconifyIconOffline
        icon="ep:collection"
        class="text-5xl mb-3 opacity-30"
      />
      <p class="text-lg">暂无投资组合，点击上方按钮创建</p>
    </div>

    <!-- 卡片列表（卡片本体见 components/PortfolioCard.vue，2026-10-30 重设计） -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <PortfolioCard
        v-for="item in portfolios"
        :key="item.id"
        :item="item"
        @open="openPortfolio"
        @delete="handleDelete"
      />
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
          <!-- 重名由后端判定（同家庭未删除组合不允许同名，409 带具体名字）。
               这里只做长度约束——把校验规则复制到前端必然与后端漂移。 -->
          <el-input
            v-model="form.name"
            placeholder="如：养老计划"
            maxlength="100"
            show-word-limit
          />
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
          <!-- #2685：选项来自后端 BENCHMARK_INDICES，不再硬编码（旧写死的 SPX 必降级） -->
          <el-select
            v-model="form.benchmark"
            class="w-full"
            clearable
            filterable
            placeholder="选择基准指数"
          >
            <el-option
              v-for="item in benchmarkOptions"
              :key="item.code"
              :label="item.name"
              :value="item.code"
            />
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
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import PortfolioCard from "@/views/asset/portfolio/components/PortfolioCard.vue";
import {
  getPortfolios,
  createPortfolio,
  deletePortfolio,
  type PortfolioItem
} from "@/api/portfolio";
import { getBenchmarks, type BenchmarkOption } from "@/api/summary";

defineOptions({ name: "PortfolioList" });

const router = useRouter();

/** 整卡点击 → 组合详情（路由留在页面，卡片组件只 emit id，便于单测） */
function openPortfolio(id: number) {
  router.push(`/asset/portfolios/${id}`);
}

/** 可选基准清单（#2685）：唯一出口是后端 `BENCHMARK_INDICES` */
const benchmarkOptions = ref<BenchmarkOption[]>([]);

async function loadBenchmarks() {
  if (benchmarkOptions.value.length) return;
  try {
    const res = await getBenchmarks();
    benchmarkOptions.value = res.data ?? [];
  } catch {
    benchmarkOptions.value = [];
  }
}

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
  void loadBenchmarks();
}

async function handleSave() {
  const name = form.value.name.trim();
  if (!name) {
    ElMessage.warning("请输入组合名称");
    return;
  }
  saving.value = true;
  try {
    await createPortfolio({
      name,
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
    // 409 = 重名，后端已给出「组合「xxx」已存在」，直接透出，不再包一层泛化文案
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
  /* 继承全局字体 token，避免与站内其它页面字体不一致（design-tokens.css --font-ui） */
  font-family: var(--font-ui);

  /* 数字等宽对齐：消除金额/计数宽度抖动（design.md「数字等宽对齐」） */
  font-variant-numeric: tabular-nums;
}

/* 卡片外观已随卡片组件迁到 components/PortfolioCard.vue（2026-10-30 重设计，
   样式与结构同处一文件，页面只负责栅格） */
</style>
