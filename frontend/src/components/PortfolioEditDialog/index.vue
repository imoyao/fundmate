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
          allow-create
        >
          <el-option label="沪深300" value="CSI300" />
          <el-option label="中证500" value="CSI500" />
          <el-option label="标普500" value="SPX" />
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
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  getPortfolios,
  updatePortfolio,
  type PortfolioDetail
} from "@/api/portfolio";
import { getLedgers, updateLedger, type LedgerItem } from "@/api/ledger";

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

watch(
  () => props.modelValue,
  visible => {
    if (visible && props.portfolio) {
      initForm();
      void loadLedgers();
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
    await updatePortfolio(current.id, editForm.value);

    // TODO(tech-debt): 账户关联差异计算（unlink/link 逐个调接口）应下沉到后端原子化接口，
    // 详见技术债务 issue（「计算前移：组合编辑的账户关联差异应由后端统一处理」）
    const previousIds = props.linkedLedgerIds;
    const toUnlink = previousIds.filter(
      id => !selectedLedgerIds.value.includes(id)
    );
    const toLink = selectedLedgerIds.value.filter(
      id => !previousIds.includes(id)
    );
    for (const id of toUnlink) {
      await updateLedger(id, { portfolio_id: null });
    }
    for (const id of toLink) {
      await updateLedger(id, { portfolio_id: current.id });
    }

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
  font-size: 12px;
  color: var(--text-tertiary);
}

.ledger-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}
</style>
