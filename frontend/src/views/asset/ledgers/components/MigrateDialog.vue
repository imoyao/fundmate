<template>
  <el-dialog
    v-model="migrateDialogVisible"
    title="迁移资产到其他账户"
    width="400px"
    destroy-on-close
    :before-close="onBeforeClose"
  >
    <el-form label-width="80px">
      <el-form-item label="资产名称"
        ><span>{{
          migratingItem?.name || migratingItem?.symbol
        }}</span></el-form-item
      >
      <el-form-item label="目标账户">
        <el-select
          v-model="migrateTargetLedgerId"
          placeholder="选择同类型账户"
          class="w-full"
        >
          <el-option
            v-for="ledger in sameTypeLedgers"
            :key="ledger.id"
            :label="ledger.name"
            :value="ledger.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <!-- 取消走 requestClose：before-close 只拦关闭按钮 / ESC / 点遮罩，程序化 close 走不到它 -->
      <el-button @click="requestClose(() => (migrateDialogVisible = false))"
        >取消</el-button
      >
      <el-button
        type="primary"
        :disabled="!migrateTargetLedgerId"
        @click="handleMigrate"
        >确认迁移</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import { type LedgerItem } from "@/api/ledger";
import { updatePosition } from "@/api/positions";
import { updateAsset } from "@/api/assets";
import { useUnsavedChangesGuard } from "@/composables/useUnsavedChangesGuard";

interface LedgerHoldingRow {
  id: number;
  symbol?: string;
  name?: string | null;
  asset_type?: string;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  avg_price?: number;
  current_price?: number;
  allocation?: string | null;
  allocation_label?: string;
  quantity?: number;
  account_name?: string;
}

const props = defineProps<{
  ledgerId: string;
  sameTypeLedgers: LedgerItem[];
}>();

const emit = defineEmits<{
  migrated: [];
}>();

const migrateDialogVisible = ref(false);
const migratingItem = ref<LedgerHoldingRow | null>(null);
const migrateTargetLedgerId = ref<number | null>(null);

// ── 未保存离开保护（#1853）──
// 本弹窗只有一个可编辑字段（目标账户），且 `openMigrateDialog` 每次都把它重置为 null，
// 所以「非 null」就等价于「用户改过」——不需要 JSON 快照。
// 迁移成功走的是程序化 `migrateDialogVisible = false`，不经 before-close，不会误弹。
const isDirty = computed(() => migrateTargetLedgerId.value !== null);

const { onBeforeClose, requestClose } = useUnsavedChangesGuard(
  () => isDirty.value,
  {
    message: "已选了目标账户，确定放弃本次迁移吗？"
  }
);

function openMigrateDialog(row: LedgerHoldingRow) {
  migratingItem.value = row;
  migrateTargetLedgerId.value = null;
  migrateDialogVisible.value = true;
}

async function handleMigrate() {
  if (!migrateTargetLedgerId.value || !migratingItem.value) return;
  const ledger = props.sameTypeLedgers.find(
    l => l.id === migrateTargetLedgerId.value
  );
  if (!ledger) return;
  try {
    if (migratingItem.value.id > 100000) {
      await updateAsset(migratingItem.value.id - 100000, {
        account_name: ledger.name
      });
    } else {
      // 归属迁移走 positions 域端点（PATCH /api/positions/<id>/ 接受 ledger_id）；
      // 原调 ledgers 域 updateLedgerPosition 传 account_name 会被后端静默丢弃（#965 修复）。
      await updatePosition(migratingItem.value.id, {
        ledger_id: ledger.id,
        account_name: ledger.name
      });
    }
    ElMessage.success(`已迁移至「${ledger.name}」`);
    migrateDialogVisible.value = false;
    // 复位目标账户选择：isDirty 就是 `migrateTargetLedgerId !== null`，不复位则它恒为 true，
    // onBeforeRouteLeave 会在离开页面时误弹「已选了目标账户，确定放弃本次迁移吗？」。
    // `openMigrateDialog` 里的重置只覆盖「下次打开」，覆盖不了「关掉就走」这条路。
    migrateTargetLedgerId.value = null;
    emit("migrated");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "迁移失败");
  }
}

defineExpose({ openMigrateDialog });
</script>
