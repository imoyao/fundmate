<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  deleteOrphanPositions,
  getOrphanDetail,
  migrateOrphanPositions,
  type OrphanDetailResponse
} from "@/api/ledger";
import {
  LEDGER_TYPE_SHORT,
  majorCategoryLabel,
  txnTypeLabel
} from "@/constants";
import { formatDate } from "@/utils/date";
import { formatQuantity } from "@/utils/format";

/**
 * 未归置持仓清理套件（#984 ledgers/index.vue 拆分）：
 * banner（汇总提示 + 三操作）+「归入现有账户」对话框 +「明细」对话框。
 * 从 index.vue 原样迁移，行为不变；数据刷新经 emit("refresh") 由父页面 fetchData 承担。
 */
const props = defineProps<{
  /** overview 中 type=deleted 的分组（count/total） */
  orphanGroup: any;
  /** 目标账户候选（禁用 orphan 虚拟行） */
  allLedgers: any[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const showMigrateDialog = ref(false);
const migrateTargetId = ref<number | null>(null);
const migrating = ref(false);
const cleaning = ref(false);

// 未归置数据明细：banner 只显示汇总，明细对话框恢复「具体是哪些数据」的可见性
const showDetailDialog = ref(false);
const detailLoading = ref(false);
const orphanDetail = ref<OrphanDetailResponse>({
  positions: [],
  assets: [],
  transactions: [],
  summary: {
    position_count: 0,
    asset_count: 0,
    transaction_count: 0,
    total_market_value: 0
  }
});

function openMigrateDialog() {
  migrateTargetId.value = null;
  showMigrateDialog.value = true;
}

// 打开未归置数据明细对话框：拉取孤儿持仓/资产/交易清单
async function openDetailDialog() {
  showDetailDialog.value = true;
  detailLoading.value = true;
  try {
    const res = await getOrphanDetail();
    orphanDetail.value = res.data ?? orphanDetail.value;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "加载明细失败");
  } finally {
    detailLoading.value = false;
  }
}

// 明细对话框 → 归入对话框：先关明细（触发 @closed 刷新），再打开归入选择
function closeDetailAndMigrate() {
  showDetailDialog.value = false;
  openMigrateDialog();
}

async function handleMigrate() {
  if (!migrateTargetId.value) {
    ElMessage.warning("请选择目标账户");
    return;
  }
  migrating.value = true;
  try {
    const res = await migrateOrphanPositions(migrateTargetId.value);
    const total = (res as any)?.data?.total ?? 0;
    ElMessage.success(`已将 ${total} 项未归置数据归入目标账户`);
    showMigrateDialog.value = false;
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "归入失败");
  } finally {
    migrating.value = false;
  }
}

async function handleOrphanCleanup() {
  try {
    await ElMessageBox.confirm(
      "确定清理全部未归置持仓吗？将同时删除关联的交易记录，此操作不可恢复。",
      "清理未归置持仓",
      {
        type: "warning",
        confirmButtonText: "确认清理",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  cleaning.value = true;
  try {
    const res = await deleteOrphanPositions();
    const data = (res as any)?.data ?? {};
    ElMessage.success(
      `已清理 ${data.position_count ?? 0} 笔持仓、${data.asset_count ?? 0} 项资产、${data.transaction_count ?? 0} 笔交易`
    );
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "清理失败");
  } finally {
    cleaning.value = false;
  }
}
</script>

<template>
  <!-- 未归置持仓提示 banner（品牌色态：brand-100 底 + brand-700 图标/文字；
       提示性信息用品牌色而非危险色，危险色仅留给删除/清理类破坏性操作） -->
  <div v-if="orphanGroup?.count > 0" class="orphan-banner mb-6">
    <div class="flex items-center gap-2 min-w-0">
      <IconifyIconOffline
        icon="ep:warning-filled"
        class="shrink-0"
        :style="{ color: 'var(--brand-700)' }"
      />
      <span class="text-sm" :style="{ color: 'var(--brand-700)' }">
        存在 {{ orphanGroup.count }} 个已删除账户的持仓，合计
        <MoneyDisplay
          :value="orphanGroup.total || 0"
          :show-sign="false"
          :auto-color="false"
          size="sm"
        />。 建议将这些持仓归入现有账户或手动清理。
      </span>
    </div>
    <div class="flex gap-2 shrink-0">
      <!-- 查看明细：次要按钮，弹出孤儿数据清单，恢复「具体是哪些数据」的可见性 -->
      <el-button size="small" @click="openDetailDialog"> 查看明细 </el-button>
      <el-button size="small" type="primary" @click="openMigrateDialog">
        归入现有账户
      </el-button>
      <el-button
        size="small"
        type="danger"
        plain
        :loading="cleaning"
        @click="handleOrphanCleanup"
      >
        清理
      </el-button>
    </div>
  </div>

  <!-- 归入未归置持仓对话框 -->
  <el-dialog
    v-model="showMigrateDialog"
    title="归入未归置持仓"
    width="420px"
    destroy-on-close
  >
    <p class="mb-4 text-sm" :style="{ color: 'var(--text-secondary)' }">
      当前有 {{ orphanGroup?.count || 0 }} 个已删除账户的持仓，合计
      <MoneyDisplay
        :value="orphanGroup?.total || 0"
        :show-sign="false"
        :auto-color="false"
        size="sm"
      />。请选择要归入的目标账户：
    </p>
    <el-select
      v-model="migrateTargetId"
      placeholder="请选择目标账户"
      filterable
      class="w-full"
    >
      <el-option
        v-for="ledger in allLedgers"
        :key="ledger.id"
        :label="ledger.name"
        :value="ledger.id"
        :disabled="ledger.id === 'orphan'"
      >
        <span>{{ ledger.name }}</span>
        <span class="ml-1 text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ LEDGER_TYPE_SHORT[ledger.ledger_type] || ledger.ledger_type }}
        </span>
      </el-option>
    </el-select>
    <template #footer>
      <el-button @click="showMigrateDialog = false">取消</el-button>
      <el-button
        type="primary"
        :loading="migrating"
        :disabled="!migrateTargetId"
        @click="handleMigrate"
      >
        确认归入
      </el-button>
    </template>
  </el-dialog>

  <!-- 未归置数据明细对话框：恢复孤儿数据「具体是哪些」的可见性（banner 只显示汇总数字） -->
  <el-dialog
    v-model="showDetailDialog"
    title="未归置数据明细"
    width="640px"
    destroy-on-close
    @closed="emit('refresh')"
  >
    <div v-loading="detailLoading">
      <p class="mb-4 text-sm" :style="{ color: 'var(--text-secondary)' }">
        共
        {{ orphanDetail.summary.position_count }} 笔持仓 /
        {{ orphanDetail.summary.asset_count }} 项资产 /
        {{ orphanDetail.summary.transaction_count }} 笔交易
      </p>

      <!-- 分区一：孤儿持仓（名称/数量/市值/盈亏） -->
      <section v-if="orphanDetail.positions.length" class="orphan-section">
        <h4 class="orphan-section-title">持仓</h4>
        <el-table :data="orphanDetail.positions">
          <el-table-column label="名称" min-width="140">
            <template #default="{ row }">
              <span class="orphan-cell-name">{{ row.name || row.symbol }}</span>
            </template>
          </el-table-column>
          <el-table-column label="数量" width="110" align="right">
            <template #default="{ row }">
              {{ formatQuantity(row.quantity) }} 份
            </template>
          </el-table-column>
          <el-table-column label="市值" width="120" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.market_value"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>
          <el-table-column label="盈亏" width="120" align="right">
            <template #default="{ row }">
              <MoneyDisplay :value="row.pnl" size="sm" />
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 分区二：孤儿资产（名称/类型/金额） -->
      <section v-if="orphanDetail.assets.length" class="orphan-section">
        <h4 class="orphan-section-title">资产</h4>
        <el-table :data="orphanDetail.assets">
          <el-table-column label="名称" min-width="140">
            <template #default="{ row }">
              <span class="orphan-cell-name">{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              {{ majorCategoryLabel(row.major_category) }}
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.amount"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 分区三：孤儿交易（持仓/类型/金额/日期） -->
      <section v-if="orphanDetail.transactions.length" class="orphan-section">
        <h4 class="orphan-section-title">交易</h4>
        <el-table :data="orphanDetail.transactions">
          <el-table-column label="交易标的" min-width="140">
            <template #default="{ row }">
              <span class="orphan-cell-name">{{ row.position_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              {{ txnTypeLabel(row.txn_type) }}
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.amount"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>
          <el-table-column label="交易日期" width="110" align="right">
            <template #default="{ row }">
              {{ formatDate(row.confirm_date) }}
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>
    <template #footer>
      <!-- 主按钮在右、危险按钮在左；清理按钮危险色走语义 token（--color-danger-system），
           覆盖 Element Plus 默认 danger（#f56c6c）以对齐设计语言 -->
      <el-button
        type="danger"
        plain
        class="orphan-clean-btn"
        :loading="cleaning"
        @click="handleOrphanCleanup"
      >
        清理
      </el-button>
      <el-button type="primary" @click="closeDetailAndMigrate">
        归入现有账户
      </el-button>
    </template>
  </el-dialog>
</template>
