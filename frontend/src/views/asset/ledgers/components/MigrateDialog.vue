<template>
  <el-dialog
    v-model="migrateDialogVisible"
    title="迁移资产到其他账户"
    width="400px"
    destroy-on-close
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
      <el-button @click="migrateDialogVisible = false">取消</el-button>
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
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { updateLedgerPosition, type LedgerItem } from "@/api/ledger";
import { updateAsset } from "@/api/assets";

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
      await updateLedgerPosition(
        Number(props.ledgerId),
        migratingItem.value.id,
        { account_name: ledger.name }
      );
    }
    ElMessage.success(`已迁移至「${ledger.name}」`);
    migrateDialogVisible.value = false;
    emit("migrated");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "迁移失败");
  }
}

defineExpose({ openMigrateDialog });
</script>
