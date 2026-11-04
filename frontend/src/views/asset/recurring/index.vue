<template>
  <div
    class="recurring-page min-h-full p-4 md:p-6"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 标题 & 操作栏 -->
    <div
      class="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between"
    >
      <div>
        <h2
          class="text-2xl font-bold whitespace-nowrap"
          :style="{ color: 'var(--text-primary)' }"
        >
          定投计划
        </h2>
        <p class="mt-1 text-sm" :style="{ color: 'var(--text-tertiary-ink)' }">
          记录每期投多少、什么时候投。执行情况按流水现算（只认关联到该计划的买入）
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <el-select
          v-model="statusFilter"
          class="w-28"
          placeholder="全部状态"
          @change="fetchPlans"
        >
          <el-option label="全部状态" value="" />
          <el-option
            v-for="(meta, key) in STATUS_META"
            :key="key"
            :label="meta.label"
            :value="key"
          />
        </el-select>
        <el-button type="primary" @click="openCreate">
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新建计划
        </el-button>
      </div>
    </div>

    <!-- 汇总卡（唯一强调色只给「每月计划投入」） -->
    <div class="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3">
      <div
        v-for="card in summaryCards"
        :key="card.label"
        class="rounded-lg border p-4"
        :style="{
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-light)'
        }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
          {{ card.label }}
        </div>
        <div
          class="mt-1 font-semibold tabular-nums"
          :style="{
            color:
              card.tone === 'key' ? 'var(--brand-ink)' : 'var(--text-primary)',
            fontSize:
              card.tone === 'key'
                ? 'var(--text-num-hero)'
                : 'var(--text-num-strong)'
          }"
        >
          {{ card.value }}
        </div>
        <div
          class="mt-1 text-xs"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        >
          {{ card.hint }}
        </div>
      </div>
    </div>

    <!-- 加载态 -->
    <div
      v-if="loading"
      class="py-20 text-center"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <el-icon class="is-loading"><Loading /></el-icon>
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="!plans.length"
      class="py-20 text-center"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <p class="mb-2">还没有定投计划</p>
      <p class="mb-4 text-sm">
        计划只做「提醒与记录」：本页不会自动下单，也不会自动生成流水
      </p>
      <el-button type="primary" @click="openCreate">新建计划</el-button>
    </div>

    <!-- 计划列表 -->
    <el-table v-else :data="plans" size="small" empty-text="暂无定投计划">
      <el-table-column label="标的" min-width="180">
        <template #default="{ row }">
          <div class="flex flex-col">
            <span class="font-medium" :style="{ color: 'var(--text-primary)' }">
              {{ row.position_name || row.symbol }}
            </span>
            <span
              class="text-xs"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              {{ row.symbol }}
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="账户" min-width="120">
        <template #default="{ row }">
          <span :style="{ color: 'var(--text-secondary)' }">
            {{ row.account_name || "未归属" }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="每期金额" width="120" align="right">
        <template #default="{ row }">
          <span class="tabular-nums" :style="{ color: 'var(--text-primary)' }">
            {{ formatYuan(row.amount) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="频率" min-width="140">
        <template #default="{ row }">
          <span :style="{ color: 'var(--text-secondary)' }">
            {{ planScheduleLabel(row as PlanRow) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="下次扣款" width="120">
        <template #default="{ row }">
          <span
            class="tabular-nums"
            :style="{ color: 'var(--text-secondary)' }"
          >
            {{ row.next_due_date || "—" }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="累计投入" width="150" align="right">
        <template #default="{ row }">
          <div class="flex flex-col items-end">
            <span
              class="tabular-nums"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ formatYuan(row.invested_amount) }}
            </span>
            <span
              class="text-xs"
              :style="{ color: 'var(--text-tertiary-ink)' }"
            >
              已执行 {{ row.executed_count }} 期
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <div class="flex flex-col items-start gap-1">
            <el-tag
              size="small"
              :type="STATUS_META[row.status as RecurringStatus].type"
            >
              {{ STATUS_META[row.status as RecurringStatus].label }}
            </el-tag>
            <span
              v-if="row.is_overdue"
              class="text-xs"
              :style="{ color: 'var(--color-warning-ink)' }"
            >
              断投 {{ row.overdue_days }} 天
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="180" align="right">
        <template #default="{ row }">
          <el-button text size="small" @click="openEdit(row as PlanRow)">
            编辑
          </el-button>
          <el-button
            v-if="row.status === 'active'"
            text
            size="small"
            @click="handleStatus(row as PlanRow, 'pause')"
          >
            暂停
          </el-button>
          <el-button
            v-else
            text
            size="small"
            @click="handleStatus(row as PlanRow, 'resume')"
          >
            恢复
          </el-button>
          <el-button
            v-if="row.status !== 'ended'"
            text
            size="small"
            type="danger"
            @click="handleStatus(row as PlanRow, 'end')"
          >
            结束
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <PlanFormDialog
      v-model="dialogVisible"
      :plan="editingPlan"
      :ledgers="ledgerOptions"
      @saved="fetchPlans"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { getLedgers } from "@/api/ledger";
import {
  endRecurringPlan,
  listRecurringPlans,
  pauseRecurringPlan,
  resumeRecurringPlan
} from "@/api/recurring";
import type { RecurringPlan, RecurringStatus } from "@/api/recurring";
import { formatAmount } from "@/utils/currency";
import PlanFormDialog from "./components/PlanFormDialog.vue";
import {
  STATUS_META,
  monthlyCommittedCents,
  planScheduleLabel
} from "./recurringModel";

defineOptions({ name: "AssetRecurring" });

/** el-table 的 slot row 无具体类型，这里收窄 */
type PlanRow = RecurringPlan;

const plans = ref<RecurringPlan[]>([]);
const loading = ref(false);
const statusFilter = ref<RecurringStatus | "">("");
const dialogVisible = ref(false);
const editingPlan = ref<RecurringPlan | null>(null);
const ledgerOptions = ref<{ id: number; name: string }[]>([]);

const formatYuan = (cents: number) => `¥${formatAmount((cents || 0) / 100, 2)}`;

const fetchPlans = async () => {
  loading.value = true;
  try {
    const res = await listRecurringPlans(statusFilter.value || undefined);
    plans.value = res.data || [];
  } catch (e) {
    ElMessage.error("定投计划加载失败");
  } finally {
    loading.value = false;
  }
};

const fetchLedgers = async () => {
  try {
    const res = await getLedgers();
    ledgerOptions.value = (res.data || []).map(item => ({
      id: item.id,
      name: item.name
    }));
  } catch (e) {
    // 账户下拉只是辅助：取不到时表单仍可保存，不阻断整页
    ledgerOptions.value = [];
  }
};

const summaryCards = computed(() => {
  const active = plans.value.filter(p => p.status === "active");
  const overdue = plans.value.filter(p => p.is_overdue);
  return [
    {
      label: "在投计划",
      value: `${active.length} 个`,
      hint: `全部 ${plans.value.length} 个（含暂停/结束）`,
      tone: "normal"
    },
    {
      label: "每月计划投入",
      value: formatYuan(monthlyCommittedCents(plans.value)),
      hint: "周投 ×4、双周投 ×2 折算，仅用于横向比较",
      tone: "key"
    },
    {
      label: "待处理",
      value: overdue.length ? `${overdue.length} 个断投` : "无",
      hint: overdue.length
        ? "最近一期应扣款已过 7 天且没有对应买入"
        : "最近一期都已执行或有宽限期",
      tone: "normal"
    }
  ];
});

const openCreate = () => {
  editingPlan.value = null;
  dialogVisible.value = true;
};

const openEdit = (plan: RecurringPlan) => {
  editingPlan.value = plan;
  dialogVisible.value = true;
};

const handleStatus = async (
  plan: RecurringPlan,
  action: "pause" | "resume" | "end"
) => {
  const labels = { pause: "暂停", resume: "恢复", end: "结束" } as const;
  if (action === "end") {
    try {
      await ElMessageBox.confirm(
        `结束后「${plan.position_name || plan.symbol}」不再推进下次扣款日，历史流水保留。可随时恢复。`,
        "结束定投计划",
        { type: "warning", confirmButtonText: "结束", cancelButtonText: "取消" }
      );
    } catch (e) {
      return;
    }
  }
  try {
    if (action === "pause") await pauseRecurringPlan(plan.id);
    else if (action === "resume") await resumeRecurringPlan(plan.id);
    else await endRecurringPlan(plan.id);
    ElMessage.success(`已${labels[action]}`);
    await fetchPlans();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || `${labels[action]}失败`);
  }
};

onMounted(() => {
  fetchPlans();
  fetchLedgers();
});
</script>
