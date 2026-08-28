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
      v-if="ledgerType === 'securities' || ledgerType === 'fund_platform'"
      label="现金账户"
    >
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

    <el-form-item label="销售机构">
      <el-select
        :model-value="salesInstitutionId"
        class="w-full"
        clearable
        filterable
        placeholder="可不选，支持汉字/别名/拼音首字母（如 ht=华泰）"
        :filter-method="filterInstitution"
        @update:model-value="onSalesInstitutionChange"
      >
        <!-- 常用机构置顶分组（is_common，按 common_sort 升序）+ 全部机构（#1081）。
             自定义 filter-method：汉字原文 / 常用别名 / 拼音首字母简拼（pinyin_short）
             三路匹配，由 visibleInstitutions computed 统一过滤，空组不渲染 -->
        <el-option-group v-if="commonInstitutions.length" label="常用机构">
          <el-option
            v-for="inst in commonInstitutions"
            :key="inst.id"
            :label="institutionLabel(inst)"
            :value="inst.id"
          >
            <div class="inst-option">
              <span class="inst-option__main">{{
                inst.display_name || inst.org_name
              }}</span>
              <span
                v-if="inst.display_name"
                class="inst-option__sub"
                :title="inst.org_name"
                >{{ inst.org_name }}</span
              >
              <span class="inst-option__tag">{{
                orgTypeGroupLabel(inst.org_type)
              }}</span>
            </div>
          </el-option>
        </el-option-group>
        <el-option-group v-if="otherInstitutions.length" label="全部机构">
          <el-option
            v-for="inst in otherInstitutions"
            :key="inst.id"
            :label="institutionLabel(inst)"
            :value="inst.id"
          >
            <div class="inst-option">
              <span class="inst-option__main">{{
                inst.display_name || inst.org_name
              }}</span>
              <span
                v-if="inst.display_name"
                class="inst-option__sub"
                :title="inst.org_name"
                >{{ inst.org_name }}</span
              >
              <span class="inst-option__tag">{{
                orgTypeGroupLabel(inst.org_type)
              }}</span>
            </div>
          </el-option>
        </el-option-group>
      </el-select>
      <!-- 银行渠道轻提示（#1082 D8）：fund 账户选中银行类机构时缓解「卡 vs 渠道」心智混淆 -->
      <p v-if="showBankChannelHint" class="bank-channel-hint">
        银行渠道购买的基金记录在此；银行卡本身资产请使用银行账户管理
      </p>
    </el-form-item>

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
          :ledger-type="ledgerType"
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
    <el-collapse
      v-if="ledgerType === 'securities' || ledgerType === 'fund_platform'"
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
import { computed, ref } from "vue";
import { LEDGER_TYPE_OPTIONS } from "@/constants";
import type { SalesInstitution, LedgerItem } from "@/api/ledger";
import type { PortfolioItem } from "@/api/portfolio";
import FeeConfigFields from "./FeeConfigFields.vue";

// ── 销售机构类型映射（#1081/#1082，AMAC 原始 11 类 org_type）──

/** AMAC 原始 org_type → 展示标签组（独立/银行/券商/保险/其他） */
const ORG_TYPE_GROUP_LABELS: Record<string, string> = {
  独立基金销售机构: "独立",
  全国性商业银行: "银行",
  城市商业银行: "银行",
  农村商业银行: "银行",
  在华外资法人银行: "银行",
  证券公司: "券商",
  证券投资咨询机构: "券商",
  保险公司: "保险",
  保险代理公司和保险经纪公司: "保险",
  期货公司: "其他",
  公募基金管理公司销售子公司: "其他"
};

/** 银行类 org_type 集合（#1082 D8 银行渠道提示判定用） */
const BANK_ORG_TYPES = new Set([
  "全国性商业银行",
  "城市商业银行",
  "农村商业银行",
  "在华外资法人银行"
]);

/**
 * 渠道分组 → 可见机构原始类型（#1082 D2/D3）：
 * - securities 仅券商（股票交易只发生在券商）
 * - fund_platform 除期货公司外全部（券商代销场外基金，靠常用置顶 + 类型标识区分）
 * - 其余类型不在表内 → 不过滤，维持现状
 */
const LEDGER_TYPE_ORG_TYPES: Record<string, string[]> = {
  securities: ["证券公司"],
  fund_platform: [
    "独立基金销售机构",
    "全国性商业银行",
    "城市商业银行",
    "农村商业银行",
    "在华外资法人银行",
    "证券公司",
    "证券投资咨询机构",
    "保险公司",
    "保险代理公司和保险经纪公司",
    "公募基金管理公司销售子公司"
  ]
};

function orgTypeGroupLabel(orgType?: string | null): string {
  return (orgType && ORG_TYPE_GROUP_LABELS[orgType]) || "其他";
}

interface Props {
  ledgerType: string;
  linkedCashId: number | null;
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

/** 销售机构下拉检索关键词（小写），由 filter-method 回写，驱动 visibleInstitutions 过滤 */
const institutionFilter = ref("");

/**
 * 按当前账户类型过滤后的机构列表。
 * 过滤在前端做而非调 API 传 org_types：ledger_type 在表单内可随时切换，
 * 四个调用方（ledgers 列表页 / 详情编辑 / 资产录入 / 导入向导）均已一次性
 * 加载全量名录经 props 传入，前端 computed 过滤零额外请求、类型切换即时生效。
 * 兼容回退：org_type 缺失（后端旧响应）的条目保持可见，避免下拉被过滤成空。
 *
 * 文本检索（#1081 用户反馈）：支持汉字原文 / 常用别名 / 拼音首字母简拼
 * （pinyin_short 由后端 AMAC job 派生）三路匹配，大小写不敏感。
 */
const visibleInstitutions = computed<SalesInstitution[]>(() => {
  const allowed = LEDGER_TYPE_ORG_TYPES[props.ledgerType];
  let list = props.salesInstitutions;
  if (allowed) {
    const allowSet = new Set(allowed);
    list = list.filter(inst => !inst.org_type || allowSet.has(inst.org_type));
  }
  const kw = institutionFilter.value;
  if (!kw) return list;
  return list.filter(
    inst =>
      inst.org_name.toLowerCase().includes(kw) ||
      (inst.display_name ?? "").toLowerCase().includes(kw) ||
      (inst.pinyin_short ?? "").toLowerCase().includes(kw)
  );
});

/** 自定义过滤入口：Element Plus 每次输入回调，记录关键词交由 computed 过滤 */
function filterInstitution(query: string) {
  institutionFilter.value = query.trim().toLowerCase();
}

/** 常用机构组：is_common=true，按 common_sort 升序（缺省排最后） */
const commonInstitutions = computed<SalesInstitution[]>(() =>
  visibleInstitutions.value
    .filter(inst => inst.is_common)
    .sort(
      (a, b) =>
        (a.common_sort ?? Number.MAX_SAFE_INTEGER) -
        (b.common_sort ?? Number.MAX_SAFE_INTEGER)
    )
);

/** 全部机构组：非常用项，维持后端默认排序（org_name 字典序） */
const otherInstitutions = computed<SalesInstitution[]>(() =>
  visibleInstitutions.value.filter(inst => !inst.is_common)
);

/** fund_platform 账户选中银行类机构时的轻提示开关（#1082 D8） */
const showBankChannelHint = computed(() => {
  if (props.ledgerType !== "fund_platform" || props.salesInstitutionId == null) {
    return false;
  }
  const inst = props.salesInstitutions.find(
    i => i.id === props.salesInstitutionId
  );
  return !!inst?.org_type && BANK_ORG_TYPES.has(inst.org_type);
});

/** 下拉展示：优先「权威全称（常用别名）」，无别名则仅全称 */
function institutionLabel(inst: SalesInstitution): string {
  return inst.display_name
    ? `${inst.org_name}（${inst.display_name}）`
    : inst.org_name;
}

function onTypeChange(val: string) {
  emit("update:ledgerType", val);
  // 如果切换到的渠道分组不是 securities/fund_platform，清空关联的现金账户
  if (val !== "securities" && val !== "fund_platform") {
    emit("update:linkedCashId", null);
    emit("update:feeConfig", null);
  }
  // 类型切换后已选机构若不在新类型的可见范围内（如 stock 下误选了非券商），自动清空。
  // 注意：emit 后 props.ledgerType 不会同步回流，此处必须基于新值 val 直接判断，
  // 不能复用 visibleInstitutions（其仍依赖旧 props 值）
  if (props.salesInstitutionId != null) {
    const allowed = LEDGER_TYPE_ORG_TYPES[val];
    if (allowed) {
      const inst = props.salesInstitutions.find(
        i => i.id === props.salesInstitutionId
      );
      // org_type 缺失视为始终可见，与 visibleInstitutions 的兼容回退语义一致
      if (inst?.org_type && !allowed.includes(inst.org_type)) {
        emit("update:salesInstitutionId", null);
      }
    }
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

<!-- 银行渠道轻提示：表单内联元素，scoped 可命中 -->
<style scoped>
.bank-channel-hint {
  margin: var(--space-3, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
}
</style>

<!--
  销售机构选项行样式：el-select 下拉面板默认 teleport 到 body，
  scoped 样式无法命中，故用非 scoped 块 + 唯一类名（inst-option__*）避免全局污染。
  颜色全部走 design token，禁止硬编码 hex。
-->
<style>
.inst-option {
  display: flex;
  gap: 8px;
  align-items: baseline;
  width: 100%;
  min-width: 0;
}

/* 主文本：常用名优先（如「支付宝」） */
.inst-option__main {
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 次级文本：常用名存在时的权威全称，小字弱化 */
.inst-option__sub {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label, 13px);
  color: var(--text-tertiary);
  white-space: nowrap;
}

/* 右侧类型标签：默认 Badge 形态（--bg-soft 底 + --text-secondary 字 + 胶囊圆角） */
.inst-option__tag {
  flex-shrink: 0;
  padding: 1px 8px;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}
</style>
