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

    <!-- 活期+绑定（#1137）：账户的「余额宝」，卖出回款可自动申购 -->
    <el-form-item
      v-if="ledgerType === 'securities' || ledgerType === 'fund_platform'"
      label="活期+"
    >
      <el-select
        :model-value="linkedMoneyFundCode"
        class="w-full"
        clearable
        filterable
        remote
        reserve-keyword
        :remote-method="searchMoneyFund"
        :loading="fundSearching"
        placeholder="搜索货币基金，如「余额宝」「水星」"
        @update:model-value="onMoneyFundChange"
      >
        <!-- 全量搜索 + 选择时限制：后端 is_money_fund 为三态，
             false（明确非货基）禁用并标注；true / null（未知）均可选，
             避免类型标注缺失的券商业内现金管理产品（如 026029）被误筛。 -->
        <el-option
          v-for="f in effectiveFundOptions"
          :key="f.code"
          :label="f.name ? `${f.name}（${f.code}）` : f.code"
          :value="f.code"
          :disabled="f.is_money_fund === false"
        >
          <span>{{ f.name ? `${f.name}（${f.code}）` : f.code }}</span>
          <span v-if="f.is_money_fund === false" class="mf-option-tag"
            >非货币基金</span
          >
        </el-option>
      </el-select>
      <p class="field-hint">
        绑定后，卖出 /
        赎回回款可自动申购该产品（类似「余额宝」）。支持场外货币基金与券商渠道现金管理产品
      </p>
    </el-form-item>

    <el-form-item
      v-if="ledgerType === 'securities' || ledgerType === 'fund_platform'"
      label="自动申购"
    >
      <el-switch
        :model-value="autoPurchaseMoneyFund"
        :disabled="!linkedMoneyFundCode"
        @update:model-value="onAutoPurchaseChange"
      />
      <p class="field-hint">
        {{
          linkedMoneyFundCode
            ? "开启后，卖出 / 赎回回款将自动申购已绑定的活期+"
            : "请先绑定活期+，再开启自动申购"
        }}
      </p>
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
import { searchFunds, type FundSearchItem } from "@/api/funds";
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
}

const props = withDefaults(defineProps<Props>(), {
  cashLedgers: () => [],
  portfolioList: () => [],
  feeConfig: null,
  salesInstitutionId: null,
  salesInstitutions: () => [],
  advancedCollapsed: false,
  linkedMoneyFundCode: null,
  linkedMoneyFundName: null,
  autoPurchaseMoneyFund: false
});

const emit = defineEmits<{
  "update:ledgerType": [value: string];
  "update:linkedCashId": [value: number | null];
  "update:linkedMoneyFundCode": [value: string | null];
  "update:autoPurchaseMoneyFund": [value: boolean];
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
  if (
    props.ledgerType !== "fund_platform" ||
    props.salesInstitutionId == null
  ) {
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
    // 渠道分组不再支持活期+时，一并解绑并关闭自动申购
    emit("update:linkedMoneyFundCode", null);
    emit("update:autoPurchaseMoneyFund", false);
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

// ── 活期+绑定（#1137）──
// 入参/出参统一用基金代码（搜索结果即 code），存储由后端转 funds.id。
// 仅货币基金可作为活期+；后端 is_money_fund 标记缺失时退回全部结果，避免筛空。

/** 远程搜索中的候选（仅当次搜索结果，不缓存全量） */
const fundOptions = ref<FundSearchItem[]>([]);
const fundSearching = ref(false);
/** 当前已选活期+的名称（用户从搜索结果中选中时回写）。
 *  独立于 props.linkedMoneyFundName：换绑后后者可能仍是旧产品名，
 *  用本值保证「重新选择产品」时下拉/回显都显示当前所选产品的名称而非裸代码（#交互修复）。 */
const selectedMoneyFundName = ref<string | null>(null);

/** 实际候选项：并入当前已绑定项，保证编辑回显时下拉里存在该选项（显示名称而非裸代码） */
const effectiveFundOptions = computed<FundSearchItem[]>(() => {
  const list = [...fundOptions.value];
  const bound = props.linkedMoneyFundCode;
  if (bound && !list.some(o => o.code === bound)) {
    // 优先用本次搜索命中的名称（用户刚选过，最准），回退到出参名称，最后兜底裸代码。
    // 注：不能用 props.linkedMoneyFundName 一项兜底——换绑后它可能仍是旧产品的名称，
    // 会导致「选了 B 却显示 A 的名字 / 或裸代码」的 bug（#交互修复）。
    list.unshift({
      code: bound,
      name: selectedMoneyFundName.value || props.linkedMoneyFundName || bound,
      type: "货币基金",
      subscription_rate: 0
    });
  }
  return list;
});

async function searchMoneyFund(query: string) {
  const kw = (query ?? "").trim();
  if (!kw) {
    fundOptions.value = [];
    return;
  }
  fundSearching.value = true;
  try {
    const res = await searchFunds(kw);
    const list = ((res as any)?.data ?? []) as FundSearchItem[];
    // 全量搜索 + 选择时限制（#活期+ 扩源）：
    // 后端 is_money_fund 已升级为三态——true=货基 / false=明确非货基 / null=类型未知。
    // 搜索阶段**不再过滤**，全部命中项都进下拉；能否选中交给 el-option 的
    // :disabled="f.is_money_fund === false" 控制。
    // 不在搜索阶段剔除的原因：本地库 fund_type_id 有 88.7% 为空，此前按
    // `fund_type_id == 6` 判定会把一批真货基误判为非货基而彻底搜不到——
    // 典型如 026029 银河水星现金添利货币（券商渠道现金管理产品，
    // 库内已同步 120 天万份收益，收益口径与场外货基一致）。
    fundOptions.value = list;
  } catch {
    fundOptions.value = [];
  } finally {
    fundSearching.value = false;
  }
}

function onMoneyFundChange(val: string | null) {
  emit("update:linkedMoneyFundCode", val ?? null);
  // 选中时回写名称（优先取搜索结果里的权威名），供 effectiveFundOptions 兜底展示用，
  // 避免重新打开下拉（远程搜索列表被清空）时回显成裸代码。
  if (val) {
    const hit = fundOptions.value.find(o => o.code === val);
    selectedMoneyFundName.value =
      hit?.name ?? props.linkedMoneyFundName ?? null;
  } else {
    selectedMoneyFundName.value = null;
  }
  // 解绑时联动关闭开关，避免残留一个无法生效的开关（后端亦会强制关闭）
  if (!val) {
    emit("update:autoPurchaseMoneyFund", false);
  }
}

function onAutoPurchaseChange(val: boolean) {
  emit("update:autoPurchaseMoneyFund", !!val);
}

function onPortfolioChange(val: number | null) {
  emit("update:portfolioId", val);
}

function onSalesInstitutionChange(val: number | null) {
  emit("update:salesInstitutionId", val);
}
</script>

<!-- 银行渠道轻提示 / 活期+说明：表单内联元素，scoped 可命中 -->
<style scoped>
.bank-channel-hint {
  margin: var(--space-3, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-secondary);
}

/* 活期+绑定与自动申购的说明文字（#1137）：辅助层级，--text-tertiary */
.field-hint {
  margin: var(--space-3, 8px) 0 0;
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary);
}

/* 活期+ 下拉中的「非货币基金」标注（全量搜索 + 选择时限制）：
   与产品名同行、弱化显示；禁用态由 el-option 自身置灰，此处只做类型提示，
   让用户理解「为什么这项选不了」，而非单纯消失不见。 */
.mf-option-tag {
  padding: 0 6px;
  margin-left: var(--space-3, 8px);
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
  border-radius: var(--radius-sm, 4px);
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
