<!--
  PortfolioEditDialog · 组合编辑对话框（强制复用，见 docs/design/components.md）
  - 从 portfolio/detail.vue 拆出的共有组件：编辑组合基本信息 + 关联账户（含账户排序、组合名映射）
  - 父页面只传 portfolio + linkedLedgerIds，保存成功后 emit("saved") 由父级刷新
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑组合"
    width="500px"
    destroy-on-close
    @update:model-value="handleVisibleChange"
  >
    <el-form :model="editForm" label-width="90px">
      <el-form-item label="组合名称" required>
        <el-input v-model="editForm.name" />
      </el-form-item>
      <el-form-item label="投资目的">
        <el-input v-model="editForm.purpose" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="editForm.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="目标收益率">
        <el-input-number
          v-model="editForm.target_return"
          :min="0"
          :max="100"
          :precision="2"
          controls-position="right"
          class="w-full"
        />
      </el-form-item>
      <el-form-item label="目标金额">
        <el-input-number
          v-model="editForm.target_amount"
          :min="0"
          :precision="2"
          controls-position="right"
          class="w-full"
        />
      </el-form-item>
      <el-form-item label="目标日期">
        <el-date-picker
          v-model="editForm.target_date"
          type="date"
          placeholder="选择日期"
          class="w-full"
          value-format="YYYY-MM-DD"
        />
      </el-form-item>
      <el-form-item label="基准指数">
        <el-select
          v-model="editForm.benchmark"
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
          <!-- 存量值（如旧的 CSI300）不在清单里：保留可选，避免一进弹窗就被清空 -->
          <el-option
            v-if="legacyBenchmark"
            :label="`${legacyBenchmark}（旧值）`"
            :value="legacyBenchmark"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="关联账户">
        <el-select
          v-model="selectedLedgerIds"
          multiple
          placeholder="选择关联此组合的账户"
          class="w-full"
          clearable
        >
          <el-option
            v-for="ledger in allLedgers"
            :key="ledger.id"
            :label="ledger.name"
            :value="ledger.id"
          >
            <div class="flex items-center justify-between w-full">
              <span>{{ ledger.name }}</span>
              <el-tag
                v-if="ledger.portfolioName"
                size="small"
                type="info"
                class="ml-2"
              >
                已关联：{{ ledger.portfolioName }}
              </el-tag>
              <span v-else class="ledger-free">待关联</span>
            </div>
          </el-option>
        </el-select>
        <p class="ledger-hint">
          一个账户只能归属一个组合，重新分配后原组合将自动解绑。优先显示未关联账户。
        </p>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleUpdate"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getPortfolios,
  updatePortfolio,
  type PortfolioDetail
} from "@/api/portfolio";
import { getBenchmarks, type BenchmarkOption } from "@/api/summary";
import { getLedgers, type LedgerItem } from "@/api/ledger";

/** 关联账户选项：账户 + 所属组合名（用于展示"已关联：XX"） */
interface LedgerOption extends LedgerItem {
  portfolio_id?: number | null;
  portfolioName?: string | null;
}

interface EditForm {
  name: string;
  purpose: string;
  description: string;
  target_return?: number;
  target_amount?: number;
  target_date: string;
  benchmark: string;
}

const props = defineProps<{
  modelValue: boolean;
  portfolio: PortfolioDetail | null;
  linkedLedgerIds: number[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const saving = ref(false);
const allLedgers = ref<LedgerOption[]>([]);
const selectedLedgerIds = ref<number[]>([]);
const editForm = ref<EditForm>({
  name: "",
  purpose: "",
  description: "",
  target_return: undefined,
  target_amount: undefined,
  target_date: "",
  benchmark: ""
});

/**
 * 可选基准清单（#2685）：唯一出口是后端 `BENCHMARK_INDICES`，前端不再硬编码。
 * 历史写死的 `SPX` 不在清单里 ⇒ 选中必走 `unrecognized_benchmark` 降级、永远显示「--」。
 */
const benchmarkOptions = ref<BenchmarkOption[]>([]);

/** 存量值不在清单里（如旧的 `CSI300`）时保留一个可选项，避免一进弹窗就被清空 */
const legacyBenchmark = computed(() => {
  const value = editForm.value.benchmark;
  if (!value) return "";
  return benchmarkOptions.value.some(item => item.code === value) ? "" : value;
});

async function loadBenchmarks() {
  if (benchmarkOptions.value.length) return;
  try {
    const res = await getBenchmarks();
    benchmarkOptions.value = res.data ?? [];
  } catch {
    // 清单拉不到时只留「旧值」选项，不阻断编辑其它字段
    benchmarkOptions.value = [];
  }
}

watch(
  () => props.modelValue,
  visible => {
    if (visible && props.portfolio) {
      initForm();
      void loadLedgers();
      void loadBenchmarks();
    }
  }
);

/** 从接口信封（{ data, message } 或 { data: { data, message } }）中安全取出列表 */
function unwrapList<T>(res: unknown): T[] {
  const d = (res as { data?: unknown })?.data;
  if (Array.isArray(d)) return d as T[];
  const nested = (d as { data?: unknown })?.data;
  return Array.isArray(nested) ? (nested as T[]) : [];
}

function initForm() {
  const p = props.portfolio;
  if (!p) return;
  editForm.value = {
    name: p.name,
    purpose: p.purpose || "",
    description: p.description || "",
    target_return: p.target_return,
    target_amount: p.target_amount,
    target_date: p.target_date || "",
    benchmark: p.benchmark || ""
  };
  selectedLedgerIds.value = [...props.linkedLedgerIds];
}

async function loadLedgers() {
  try {
    const [ledgerRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPortfolios()
    ]);
    const rawLedgers = unwrapList<LedgerOption>(ledgerRes);
    const allPortfolios = unwrapList<PortfolioDetail>(portfolioRes);

    // 组合 ID -> 名称映射（排除当前正在编辑的组合本身）
    const portfolioNameMap: Record<number, string> = {};
    const currentId = props.portfolio?.id;
    allPortfolios.forEach(p => {
      if (p.id !== currentId) {
        portfolioNameMap[p.id] = p.name;
      }
    });

    // 给每个账户附加 portfolioName，未关联的排在最前
    allLedgers.value = rawLedgers
      .map(l => ({
        ...l,
        portfolioName: l.portfolio_id
          ? portfolioNameMap[l.portfolio_id] || "未知组合"
          : null
      }))
      .sort((a, b) => {
        if (a.portfolioName && !b.portfolioName) return 1;
        if (!a.portfolioName && b.portfolioName) return -1;
        return a.name.localeCompare(b.name, "zh-Hans");
      });
  } catch {
    allLedgers.value = [];
  }
}

async function handleUpdate() {
  const current = props.portfolio;
  if (!current) return;
  if (!editForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  saving.value = true;
  try {
    // #981：账户关联只传「完整目标集合」，diff/解绑/绑定由后端事务内原子完成。
    // 原「前端算 diff + 逐个 updateLedger」有两笔债务：逻辑无法被其它入口复用；
    // 多次请求非原子，中途失败留下半更新状态——均已随本卡下沉后端。
    await updatePortfolio(current.id, {
      ...editForm.value,
      ledger_ids: selectedLedgerIds.value
    });

    ElMessage.success("组合已更新");
    emit("saved");
    handleClose();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}

function handleVisibleChange(value: boolean) {
  emit("update:modelValue", value);
}

function handleClose() {
  emit("update:modelValue", false);
}
</script>

<style lang="scss" scoped>
.ledger-free {
  margin-left: 8px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.ledger-hint {
  margin-top: 4px;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}
</style>
