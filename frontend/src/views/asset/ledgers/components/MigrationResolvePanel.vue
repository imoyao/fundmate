<template>
  <BatchMigrateDialog
    v-model:visible="batchMigrateVisible"
    v-model:target-ledger-id="batchTargetLedgerId"
    :ledgers="ledgers"
    :account-info="accountInfo"
    :sales-institutions="salesInstitutions"
    :account-name="accountName"
    :same-type-ledgers="sameTypeLedgers"
    :loading="migrationPreviewLoading"
    @preview="m.handlePreviewMigration"
  />
  <MigrationResolveDialog
    v-model:visible="migrationPanelVisible"
    v-model:resolutions="resolutions"
    :preview="migrationPreview"
    :account-name="accountName"
    :target-ledger-name="targetLedgerName"
    :pending-count="pendingCount"
    :footer-status-text="footerStatusText"
    :loading="migrationCommitting"
    @commit="m.handleCommitMigration"
    @cancel="migrationPanelVisible = false"
  />
</template>

<script setup lang="ts">
import type { LedgerItem, SalesInstitution } from "@/api/ledger";
import { useBatchMigration } from "@/composables/useBatchMigration";
import BatchMigrateDialog from "./BatchMigrateDialog.vue";
import MigrationResolveDialog from "./MigrationResolveDialog.vue";

const props = defineProps<{
  ledgers: LedgerItem[];
  accountInfo: LedgerItem | null;
  salesInstitutions: SalesInstitution[];
  ledgerId: string;
  accountName: string;
  sameTypeLedgers: LedgerItem[];
}>();

const emit = defineEmits<{
  committed: [];
}>();

const m = useBatchMigration(props, { onCommitted: () => emit("committed") });

const {
  batchMigrateVisible,
  batchTargetLedgerId,
  migrationPanelVisible,
  migrationPreview,
  migrationPreviewLoading,
  migrationCommitting,
  resolutions,
  targetLedgerName,
  pendingCount,
  footerStatusText
} = m;

defineExpose({ openBatchMigrateDialog: m.openBatchMigrateDialog });
</script>
