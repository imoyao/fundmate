<template>
  <div>
    <!-- 编辑场景只读（#2980）：分组决定后端派生的计算口径，改了只会吃到 409
         「分组与派生口径不一致」。与其让用户试错后被拒，不如直接不给改。 -->
    <el-form-item v-if="categoryReadonly" label="账户类型">
      <div class="type-readonly">
        <span class="type-readonly__value">{{ categoryLabel }}</span>
        <span class="type-readonly__hint">
          决定统计与费率口径，不可修改；如需更换请归档后新建
        </span>
      </div>
    </el-form-item>
    <el-form-item v-else label="账户类型">
      <el-select
        :model-value="channelCategory"
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

    <el-form-item v-if="canLinkCashAccount(channelCategory)" label="现金账户">
      <el-select
        :model-value="linkedCashId"
        class="w-full"
        clearable
        placeholder="选择现金/活钱账户"
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

    <!-- 活期+绑定 + 自动申购（#1137）：「账户的余额宝」，卖出回款可自动申购 -->
    <MoneyFundBindingFields
      v-if="canLinkCashAccount(channelCategory)"
      :model-value="linkedMoneyFundCode"
      :fund-name="linkedMoneyFundName"
      :auto-purchase="autoPurchaseMoneyFund"
      @update:model-value="emit('update:linkedMoneyFundCode', $event)"
      @update:auto-purchase="emit('update:autoPurchaseMoneyFund', $event)"
    />

    <!-- 销售机构：按账户类型过滤 + 常用置顶 + 三路检索（见 SalesInstitutionSelect） -->
    <SalesInstitutionSelect
      :model-value="salesInstitutionId"
      :channel-category="channelCategory"
      :institutions="salesInstitutions"
      @update:model-value="emit('update:salesInstitutionId', $event)"
    />

    <!-- 高级设置：投资组合 + 费率（导入场景下默认折叠收起） -->
    <el-collapse v-if="advancedCollapsed" class="mt-4">
      <el-collapse-item title="高级设置（组合与费率）" name="adv">
        <el-form-item label="投资组合">
          <el-select
            :model-value="portfolioId"
            class="w-full"
            clearable
            placeholder="不选择组合"
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
          :channel-category="channelCategory"
          :fee-config="feeConfig"
          @update:fee-config="emit('update:feeConfig', $event)"
        />
      </el-collapse-item>
    </el-collapse>

    <template v-else>
      <el-form-item label="投资组合">
        <el-select
          :model-value="portfolioId"
          class="w-full"
          clearable
          placeholder="不选择组合"
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
      <el-collapse v-if="canLinkCashAccount(channelCategory)" class="mt-4">
        <el-collapse-item title="高级设置（费率）" name="fee">
          <FeeConfigFields
            :channel-category="channelCategory"
            :fee-config="feeConfig"
            @update:fee-config="emit('update:feeConfig', $event)"
          />
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { FeeConfigLike } from "./ledgerTypes";
import { computed } from "vue";
import { LEDGER_TYPE_OPTIONS } from "@/constants";
import type { SalesInstitution, LedgerItem } from "@/api/ledger";
import type { PortfolioItem } from "@/api/portfolio";
import FeeConfigFields from "./FeeConfigFields.vue";
import MoneyFundBindingFields from "./MoneyFundBindingFields.vue";
import SalesInstitutionSelect from "./SalesInstitutionSelect.vue";
import {
  canLinkCashAccount,
  isInstitutionAllowedForLedgerType
} from "./accountFormModel";

/**
 * 账户表单的公共字段（#980 拆分）。
 *
 * 四个调用方共用：ledgers 列表页 / 账户详情编辑 / 资产录入 / 导入向导。
 * 原文件 587 行把「销售机构检索」「活期+远程搜索」「费率/组合折叠」全挤在一起；
 * 现在三段各有宿主：
 * - `SalesInstitutionSelect.vue`：机构下拉 + 常用置顶 + 银行渠道提示；
 * - `MoneyFundBindingFields.vue`：活期+ 远程搜索 + 自动申购联动；
 * - `accountFormModel.ts`：机构类型映射与过滤口径（纯函数，可单测）。
 * 本文件只保留账户类型 / 现金账户 / 投资组合 / 费率编排与类型切换的清理逻辑。
 */
const props = withDefaults(
  defineProps<{
    channelCategory: string;
    /** 编辑场景：分组只读展示（不可改口径），默认 false 保留创建时的下拉 */
    categoryReadonly?: boolean;
    linkedCashId: number | null;
    /** 绑定的活期+基金代码（「余额宝」概念 #1137；null=未绑定） */
    linkedMoneyFundCode?: string | null;
    /** 绑定产品名称（出参回显用；远程搜索未触发时也能显示名称而非裸代码） */
    linkedMoneyFundName?: string | null;
    /** 卖出/赎回回款是否自动申购绑定的活期+（#1137，默认关闭） */
    autoPurchaseMoneyFund?: boolean;
    portfolioId: number | null;
    cashLedgers?: LedgerItem[];
    portfolioList?: PortfolioItem[];
    feeConfig?: Record<string, unknown> | null; // 初始费率对象
    /** 已选择的基金销售机构 id（null=未选择） */
    salesInstitutionId?: number | null;
    /** 销售机构候选列表（AMAC 名录，父组件加载传入） */
    salesInstitutions?: SalesInstitution[];
    /** 导入场景用：把"投资组合 + 费率"整体折叠收起，默认展开 */
    advancedCollapsed?: boolean;
  }>(),
  {
    cashLedgers: () => [],
    portfolioList: () => [],
    feeConfig: null,
    salesInstitutionId: null,
    salesInstitutions: () => [],
    advancedCollapsed: false,
    categoryReadonly: false,
    linkedMoneyFundCode: null,
    linkedMoneyFundName: null,
    autoPurchaseMoneyFund: false
  }
);

const emit = defineEmits<{
  "update:channelCategory": [value: string];
  "update:linkedCashId": [value: number | null];
  "update:linkedMoneyFundCode": [value: string | null];
  "update:autoPurchaseMoneyFund": [value: boolean];
  "update:portfolioId": [value: number | null];
  "update:feeConfig": [value: FeeConfigLike | null];
  "update:salesInstitutionId": [value: number | null];
}>();

/** 只读态展示分组的中文名；未在选项表内时回退原值，避免出现空白 */
const categoryLabel = computed(
  () =>
    LEDGER_TYPE_OPTIONS.find(o => o.value === props.channelCategory)?.label ??
    props.channelCategory
);

function onTypeChange(val: string) {
  emit("update:channelCategory", val);
  // 切换到的渠道分组不再支持证券侧字段时，清空关联项（判据与模板同源）
  if (!canLinkCashAccount(val)) {
    emit("update:linkedCashId", null);
    emit("update:feeConfig", null);
    // 渠道分组不再支持活期+时，一并解绑并关闭自动申购
    emit("update:linkedMoneyFundCode", null);
    emit("update:autoPurchaseMoneyFund", false);
  }
  // 类型切换后已选机构若不在新类型的可见范围内（如 stock 下误选了非券商），自动清空。
  // 注意：emit 后 props.channelCategory 不会同步回流，此处必须基于新值 val 直接判断，
  // 不能复用子组件的 visibleInstitutions（其仍依赖旧 props 值）
  if (props.salesInstitutionId != null) {
    const inst = props.salesInstitutions.find(
      i => i.id === props.salesInstitutionId
    );
    if (!isInstitutionAllowedForLedgerType(inst, val)) {
      emit("update:salesInstitutionId", null);
    }
  }
}

function onCashChange(val: number | null) {
  emit("update:linkedCashId", val);
}

function onPortfolioChange(val: number | null) {
  emit("update:portfolioId", val);
}
</script>

<style scoped>
.type-readonly {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: baseline;
}

.type-readonly__value {
  font-weight: 500;
  color: var(--text-primary);
}

.type-readonly__hint {
  font-size: var(--text-label, 13px);
  color: var(--text-secondary);
}
</style>
