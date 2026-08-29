<template>
  <!-- 第一步：选择目标账户（批量迁移） -->
  <el-dialog
    v-model="visibleProxy"
    title="批量迁移持仓"
    width="400px"
    destroy-on-close
  >
    <p class="mb-4" :style="{ color: 'var(--text-secondary)' }">
      将账户「{{
        accountName
      }}」下的全部持仓与资产并入目标账户。先预览迁移方案，确认无误后才会写入。
    </p>
    <el-form label-width="80px">
      <el-form-item label="目标账户">
        <el-select
          v-model="targetLedgerIdProxy"
          class="w-full"
          placeholder="选择同类型账户"
        >
          <!-- 同销售机构候选排最前并标注机构名（软优先，见 batchTargetOptions） -->
          <el-option
            v-for="opt in batchTargetOptions"
            :key="opt.ledger.id"
            :label="opt.ledger.name"
            :value="opt.ledger.id"
          >
            <div class="mig-option">
              <span class="mig-option__name">{{ opt.ledger.name }}</span>
              <span
                v-if="opt.institutionName"
                class="mig-option__inst"
                :class="{ 'is-same': opt.sameInstitution }"
                >{{ opt.institutionName }}</span
              >
            </div>
          </el-option>
        </el-select>
      </el-form-item>
    </el-form>
    <p v-if="migrationBindingHint" class="mig-bind-hint">
      {{ migrationBindingHint }}
    </p>
    <template #footer>
      <el-button @click="visibleProxy = false">取消</el-button>
      <el-button
        type="primary"
        :disabled="!targetLedgerId"
        :loading="loading"
        @click="$emit('preview')"
      >
        预览迁移方案
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { LedgerItem, SalesInstitution } from "@/api/ledger";
import {
  salesInstitutionName,
  MIGRATION_UNBOUND_HINT,
  type MigrationTargetOption
} from "@/composables/useBatchMigration";

const props = defineProps<{
  visible: boolean;
  targetLedgerId: number | null;
  ledgers: LedgerItem[];
  accountInfo: LedgerItem | null;
  salesInstitutions: SalesInstitution[];
  accountName: string;
  sameTypeLedgers: LedgerItem[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  "update:targetLedgerId": [value: number | null];
  preview: [];
}>();

const visibleProxy = computed({
  get: () => props.visible,
  set: (v: boolean) => emit("update:visible", v)
});

const targetLedgerIdProxy = computed({
  get: () => props.targetLedgerId,
  set: (v: number | null) => emit("update:targetLedgerId", v)
});

/**
 * 批量迁移目标候选：同销售机构优先（软优先策略）——
 * 同机构候选排最前并标注机构名，其余保持原排序；不禁止跨机构，仅影响排序与默认选中。
 */
const batchTargetOptions = computed<MigrationTargetOption[]>(() => {
  const sourceInstId = props.accountInfo?.sales_institution_id ?? null;
  const candidates = props.sameTypeLedgers.map(l => ({
    ledger: l,
    institutionId: l.sales_institution_id ?? null,
    institutionName: salesInstitutionName(
      l.sales_institution_id,
      props.salesInstitutions
    ),
    sameInstitution:
      !!sourceInstId &&
      !!l.sales_institution_id &&
      l.sales_institution_id === sourceInstId
  }));
  // 稳定分组：同机构在前，其余保持原顺序
  return [
    ...candidates.filter(c => c.sameInstitution),
    ...candidates.filter(c => !c.sameInstitution)
  ];
});

/** 未绑定提示：已选目标或源账本缺销售机构绑定时给出归账建议 */
const migrationBindingHint = computed(() => {
  const selected = batchTargetOptions.value.find(
    o => o.ledger.id === props.targetLedgerId
  );
  if (
    (selected && !selected.institutionId) ||
    !props.accountInfo?.sales_institution_id
  ) {
    return MIGRATION_UNBOUND_HINT;
  }
  return "";
});
</script>

<style scoped>
/* ===== 目标账户选择器：机构标注与未绑定提示 ===== */

/* 下拉选项：名称居左、销售机构标注居右 */
.mig-option {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
}

.mig-option__name {
  color: var(--text-primary);
}

.mig-option__inst {
  flex-shrink: 0;
  padding: 0 8px;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

/* 同机构候选高亮为品牌软色（「优先候补」软按钮语义，允许引用 --brand-*） */
.mig-option__inst.is-same {
  color: var(--brand-700);
  background: var(--brand-100);
}

/* 未绑定销售机构的提示文案 */
.mig-bind-hint {
  margin: var(--space-1) 0 0;
  font-size: 12px;
}
</style>
