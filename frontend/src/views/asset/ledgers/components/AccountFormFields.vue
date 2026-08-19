<template>
  <div>
    <el-form-item label="账户类型">
      <el-select
        :model-value="ledgerType"
        class="w-full"
        @update:model-value="onTypeChange"
      >
        <el-option
          v-for="opt in LEDGER_TYPE_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </el-form-item>

    <el-form-item
      v-if="ledgerType === 'stock' || ledgerType === 'fund'"
      label="关联现金账户"
    >
      <el-select
        :model-value="linkedCashId"
        class="w-full"
        clearable
        placeholder="选择关联的现金/活钱账户"
        @update:model-value="onCashChange"
      >
        <el-option
          v-for="ledger in cashLedgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        />
      </el-select>
    </el-form-item>

    <el-form-item label="关联投资组合">
      <el-select
        :model-value="portfolioId"
        class="w-full"
        clearable
        placeholder="不关联组合"
        @update:model-value="onPortfolioChange"
      >
        <el-option
          v-for="p in portfolioList"
          :key="p.id"
          :label="p.name"
          :value="p.id"
        />
      </el-select>
    </el-form-item>

    <el-form-item label="关联销售机构">
      <el-select
        :model-value="salesInstitutionId"
        class="w-full"
        clearable
        filterable
        placeholder="不关联（可选）"
        @update:model-value="onSalesInstitutionChange"
      >
        <el-option
          v-for="inst in salesInstitutions"
          :key="inst.id"
          :label="institutionLabel(inst)"
          :value="inst.id"
        />
      </el-select>
    </el-form-item>

    <!-- 高级设置：关联投资组合 + 费率（导入场景下默认折叠收起） -->
    <el-collapse v-if="advancedCollapsed" class="mt-4">
      <el-collapse-item title="高级设置（关联与费率）" name="adv">
        <el-form-item label="关联投资组合">
          <el-select
            :model-value="portfolioId"
            class="w-full"
            clearable
            placeholder="不关联组合"
            @update:model-value="onPortfolioChange"
          >
            <el-option
              v-for="p in portfolioList"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <FeeConfigFields
          :ledger-type="ledgerType"
          :fee-config="feeConfig"
          @update:fee-config="emit('update:feeConfig', $event)"
        />
      </el-collapse-item>
    </el-collapse>

    <template v-else>
      <el-form-item label="关联投资组合">
        <el-select
          :model-value="portfolioId"
          class="w-full"
          clearable
          placeholder="不关联组合"
          @update:model-value="onPortfolioChange"
        >
          <el-option
            v-for="p in portfolioList"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
      </el-form-item>

      <!-- 高级设置：费率信息 -->
      <el-collapse
        v-if="ledgerType === 'stock' || ledgerType === 'fund'"
        class="mt-4"
      >
        <el-collapse-item title="高级设置（费率）" name="fee">
          <FeeConfigFields
            :ledger-type="ledgerType"
            :fee-config="feeConfig"
            @update:fee-config="emit('update:feeConfig', $event)"
          />
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup lang="ts">
import { LEDGER_TYPE_OPTIONS } from "@/constants";
import type { SalesInstitution } from "@/api/ledger";
import FeeConfigFields from "./FeeConfigFields.vue";

interface Props {
  ledgerType: string;
  linkedCashId: number | null;
  portfolioId: number | null;
  cashLedgers?: any[];
  portfolioList?: any[];
  feeConfig?: any; // 初始费率对象
  /** 已关联的基金销售机构 id（null=不关联） */
  salesInstitutionId?: number | null;
  /** 销售机构候选列表（AMAC 名录，父组件加载传入） */
  salesInstitutions?: SalesInstitution[];
  /** 导入场景用：把"关联投资组合 + 费率"整体折叠收起，默认展开 */
  advancedCollapsed?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  cashLedgers: () => [],
  portfolioList: () => [],
  feeConfig: null,
  salesInstitutionId: null,
  salesInstitutions: () => [],
  advancedCollapsed: false
});

const emit = defineEmits<{
  "update:ledgerType": [value: string];
  "update:linkedCashId": [value: number | null];
  "update:portfolioId": [value: number | null];
  "update:feeConfig": [value: any];
  "update:salesInstitutionId": [value: number | null];
}>();

/** 下拉展示：优先「权威全称（常用别名）」，无别名则仅全称 */
function institutionLabel(inst: SalesInstitution): string {
  return inst.display_name
    ? `${inst.org_name}（${inst.display_name}）`
    : inst.org_name;
}

function onTypeChange(val: string) {
  emit("update:ledgerType", val);
  // 如果切换到的类型不是 stock/fund，清空关联的现金账户
  if (val !== "stock" && val !== "fund") {
    emit("update:linkedCashId", null);
    emit("update:feeConfig", null);
  }
}

function onCashChange(val: number | null) {
  emit("update:linkedCashId", val);
}

function onPortfolioChange(val: number | null) {
  emit("update:portfolioId", val);
}

function onSalesInstitutionChange(val: number | null) {
  emit("update:salesInstitutionId", val);
}
</script>
