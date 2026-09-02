<template>
  <div
    class="inventory-home p-4 md:p-8 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 -->
    <div class="mb-10">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        全面盘点
      </h2>
      <p class="text-sm mt-3" :style="{ color: 'var(--text-tertiary)' }">
        选择资产大类，快速录入或导入
      </p>
    </div>

    <!-- 顶部资产分类标签栏 -->
    <div class="grid grid-cols-3 md:grid-cols-6 gap-4 mb-8">
      <div
        v-for="cat in categories"
        :key="cat.key"
        class="category-tab"
        :class="{ active: activeCategory === cat.key }"
        :style="getCategoryTabStyle(cat.key)"
        @click="activeCategory = cat.key"
      >
        <span class="category-tab-label">{{ cat.label }}</span>
        <span class="category-tab-amount">
          <template v-if="Math.abs(getCategoryTotal(cat.key)) > 0">
            <MoneyDisplay
              :value="getCategoryTotal(cat.key)"
              :show-sign="true"
              :show-currency="true"
              size="sm"
            />
          </template>
          <span
            v-else
            class="text-sm"
            :style="{ color: 'var(--text-tertiary)' }"
          >
            无记录
          </span>
        </span>
        <span v-if="activeCategory === cat.key" class="category-tab-arrow">
          <IconifyIconOffline icon="ep:caret-bottom" />
        </span>
      </div>
    </div>

    <!-- 下方内容区域 -->
    <div class="content-area">
      <!-- 第一层：大类注释卡片 -->
      <div
        class="mb-10 rounded-xl p-6 flex items-start gap-3"
        :style="{ backgroundColor: 'var(--bg-soft)' }"
      >
        <IconifyIconOffline
          icon="ep:info-filled"
          class="text-xl mt-0.5 shrink-0"
          :style="{ color: 'var(--text-tertiary)' }"
        />
        <p
          class="text-sm leading-relaxed"
          :style="{ color: 'var(--text-secondary)' }"
        >
          {{ activeCategoryDesc }}
        </p>
      </div>

      <!-- ==================== 场景 A：投资理财 ==================== -->
      <template v-if="activeCategory === 'investment'">
        <!-- 1. 投资分布（统一 mt-10 mb-10） -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          投资分布
        </h4>
        <div
          v-if="investmentGroups.length > 0"
          class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 mb-8 mt-4"
        >
          <div
            v-for="group in investmentGroups"
            :key="group.type"
            class="summary-card-item rounded-xl p-6 sm:p-8 transition-all"
            :style="{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-raised)'
            }"
          >
            <div class="flex items-center gap-3">
              <div
                class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                :style="{
                  backgroundColor: getColorWithAlpha(group.color, 0.2)
                }"
              >
                <IconifyIconOffline
                  :icon="group.icon"
                  class="text-lg"
                  :style="{ color: group.color }"
                />
              </div>
              <div>
                <p
                  class="font-medium text-sm"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  {{ group.label }}
                </p>
                <p
                  class="text-xs mt-1"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  {{ group.count }} 项 ·<MoneyDisplay
                    :value="group.total"
                    :show-sign="false"
                    :auto-color="false"
                    size="xs"
                  />
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 快捷操作（统一 mt-10 mb-10，容器 mb-8） -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          快捷操作
        </h4>
        <div
          class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-8 mt-4"
        >
          <div
            class="summary-card-item rounded-xl p-5 sm:p-6 cursor-pointer transition-all"
            :style="{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-raised)'
            }"
            @click="$router.push('/investment/manual')"
          >
            <div class="flex items-center gap-3">
              <div
                class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                :style="{
                  backgroundColor: getColorWithAlpha('var(--brand-700)', 0.2)
                }"
              >
                <IconifyIconOffline
                  icon="ep:trend-charts"
                  class="text-lg"
                  :style="{ color: 'var(--brand-700)' }"
                />
              </div>
              <div>
                <p
                  class="font-medium text-sm"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  记录投资交易
                </p>
                <p
                  class="text-xs mt-1"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  记录股票、基金、可转债、ETF
                </p>
              </div>
            </div>
          </div>

          <div
            class="summary-card-item rounded-xl p-5 sm:p-6 cursor-pointer transition-all"
            :style="{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-raised)'
            }"
            @click="$router.push('/inventory/investment/import')"
          >
            <div class="flex items-center gap-3">
              <div
                class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                :style="{
                  backgroundColor: getColorWithAlpha('var(--brand-700)', 0.2)
                }"
              >
                <IconifyIconOffline
                  icon="ep:upload"
                  class="text-lg"
                  :style="{ color: 'var(--brand-700)' }"
                />
              </div>
              <div>
                <p
                  class="font-medium text-sm"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  导入投资记账
                </p>
                <p
                  class="text-xs mt-1"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  批量导入基金/股票交割单
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- 3. 持仓明细（统一 mt-10 mb-10） -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          持仓明细
        </h4>
        <div
          class="rounded-xl p-6 sm:p-8 flex flex-col mt-4"
          :style="{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-default)',
            boxShadow: 'var(--shadow-raised)'
          }"
        >
          <el-table
            v-loading="investmentLoading"
            height="400"
            :data="investmentPositions"
            style="width: 100%"
            :header-cell-style="{
              color: 'var(--text-tertiary)',
              fontWeight: '500',
              fontSize: '13px'
            }"
            :cell-style="{ color: 'var(--text-secondary)' }"
          >
            <el-table-column
              label="产品信息"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <ProductDisplay
                  :name="row.name"
                  :symbol="row.symbol"
                  :type-label="row.type_label"
                />
              </template>
            </el-table-column>
            <el-table-column prop="account_name" label="归属账户" width="120" />
            <el-table-column label="市值" width="130" align="right">
              <template #default="{ row }">
                <MoneyDisplay
                  :value="row.market_value"
                  :show-sign="false"
                  size="sm"
                />
              </template>
            </el-table-column>
            <el-table-column label="盈亏" width="130" align="right">
              <template #default="{ row }">
                <MoneyDisplay :value="row.pnl" :show-sign="true" size="sm" />
              </template>
            </el-table-column>
          </el-table>

          <div class="flex justify-end mt-4">
            <el-pagination
              v-model:current-page="investmentPage"
              :page-size="10"
              :total="investmentTotal"
              layout="prev, pager, next"
              small
            />
          </div>
        </div>
      </template>

      <!-- ==================== 场景 B：其他大类 ==================== -->
      <template v-else>
        <!-- 1. 快捷操作（顺序调整到资产明细上方，mt-10 mb-10） -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          快捷操作
        </h4>
        <div
          class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mb-8 mt-4"
        >
          <div
            v-for="type in activeAssetTypes"
            :key="type.key"
            class="summary-card-item rounded-xl p-5 sm:p-6 cursor-pointer transition-all"
            :style="{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-raised)'
            }"
            @click="handleAddType(type.key)"
          >
            <div class="flex items-center gap-3">
              <div
                class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                :style="{ backgroundColor: getColorWithAlpha(type.color, 0.2) }"
              >
                <IconifyIconOffline
                  :icon="type.icon"
                  class="text-lg"
                  :style="{ color: type.color }"
                />
              </div>
              <div>
                <p
                  class="font-medium text-sm"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  {{ type.label }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 资产明细（统一 mt-10 mb-10） -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          资产明细
        </h4>
        <div
          v-if="currentAssets.length > 0"
          class="rounded-xl p-6 sm:p-8"
          :style="{
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-default)',
            boxShadow: 'var(--shadow-raised)'
          }"
        >
          <el-table
            :height="currentAssets.length >= 5 ? 400 : null"
            :data="currentAssets"
            style="width: 100%"
            :header-cell-style="{
              color: 'var(--text-tertiary)',
              fontWeight: '500',
              fontSize: '13px'
            }"
            :cell-style="{ color: 'var(--text-secondary)' }"
          >
            <el-table-column
              label="产品信息"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <ProductDisplay
                  :name="row.name"
                  :symbol="row.symbol"
                  :type-label="row.type_label"
                />
              </template>
            </el-table-column>
            <el-table-column
              prop="account_name"
              label="归属账户"
              width="120"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{
                row.account_name || "未指定"
              }}</template>
            </el-table-column>
            <el-table-column label="大类" width="100">
              <template #default="{ row }">
                {{ getMajorCategoryLabel(row.major_category) }}
              </template>
            </el-table-column>
            <!-- 🔥 修复：使用 signed_amount 显示正负值 -->
            <el-table-column label="金额" width="130" align="right">
              <template #default="{ row }">
                <MoneyDisplay
                  :value="row.signed_amount"
                  :show-sign="true"
                  size="sm"
                />
              </template>
            </el-table-column>
            <el-table-column label="配置目标" width="100" align="center">
              <template #default="{ row }">
                <span
                  class="px-2 py-0.5 rounded-full text-xs"
                  :style="{
                    backgroundColor: getAllocBgColor(row.allocation),
                    color: getAllocColor(row.allocation)
                  }"
                >
                  {{ getAllocLabel(row.allocation) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button text size="small" @click="openEditAssetDialog(row)"
                  >编辑</el-button
                >
                <el-button
                  text
                  size="small"
                  type="danger"
                  @click="confirmDeleteAsset(row)"
                  >删除</el-button
                >
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div
          v-else
          class="rounded-xl py-6 sm:py-8 px-10 text-center border border-dashed mt-4"
          :style="{
            borderColor: 'var(--border-default)',
            backgroundColor: 'var(--bg-card)'
          }"
        >
          <p :style="{ color: 'var(--text-tertiary)' }">
            暂无此分类下的资产记录
          </p>
        </div>
      </template>
    </div>

    <!-- 编辑资产弹窗 -->
    <el-dialog
      v-model="editAssetDialogVisible"
      title="编辑资产"
      width="420px"
      destroy-on-close
    >
      <el-form :model="editAssetForm" label-width="80px">
        <el-form-item label="金额">
          <el-input-number
            v-model="editAssetForm.amount"
            :precision="2"
            :min="0"
            class="w-full"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="editAssetForm.notes"
            type="textarea"
            :rows="2"
            placeholder="选填"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editAssetDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingAsset" @click="saveAssetEdit"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { getCssVar } from "@/composables/echarts/theme";
import { ElMessage, ElMessageBox } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getAssets,
  getAssetsSummary,
  updateAsset,
  deleteAsset
} from "@/api/assets";
import { getPositions } from "@/api/positions";
import type { Position } from "@/api/types";
import { getDistributions, getPositionGroups } from "@/api/summary";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { ALLOCATION_OPTIONS } from "@/constants";

defineOptions({ name: "InventoryHome" });

const router = useRouter();
const route = useRoute();

const categories = [
  {
    key: "investment",
    label: "投资理财",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "追求保值增值的钱。股票、基金、可转债、银行定期存款、大额存单、银行理财、国债等。这些钱牺牲了部分流动性以换取更高收益。"
  },
  {
    key: "cash",
    label: "流动资金",
    bgVar: "--category-cash-bg",
    borderVar: "--category-cash",
    desc: "用于日常消费和应急的活钱。银行卡活期、微信/支付宝余额、余额宝等随时可取的货币基金请放这里。如果这笔钱3个月内肯定不用，建议记入投资理财。"
  },
  {
    key: "fixed",
    label: "固定资产",
    bgVar: "--category-fixed-bg",
    borderVar: "--category-fixed",
    desc: "用于投资或自用的、流动性低的实物类资产。"
  },
  {
    key: "liability",
    label: "负债",
    bgVar: "--category-liability-bg",
    borderVar: "--category-liability",
    desc: "家庭需偿还的债务，如信用卡、房贷、车贷、个人借款等。"
  },
  {
    key: "receivable",
    label: "应收款",
    bgVar: "--category-receivable-bg",
    borderVar: "--category-receivable",
    desc: "家庭资产中应收未收的款项，如借给他人的钱，为他人垫付的资金。"
  },
  {
    key: "insurance",
    label: "保险项目",
    bgVar: "--category-insurance-bg",
    borderVar: "--category-insurance",
    desc: "家庭保障类资产，如寿险、健康险、年金险等。"
  },
  {
    key: "bank_wealth",
    label: "银行理财",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "银行发行的理财产品，如净值型理财、结构性存款等。"
  },
  {
    key: "advisory",
    label: "投顾",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "投资顾问/基金投顾组合类资产。"
  },
  {
    key: "trust",
    label: "信托",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "信托计划类资产。"
  },
  {
    key: "private_fund",
    label: "私募",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "私募证券/股权类基金产品。"
  },
  {
    key: "wealth_insurance",
    label: "理财型保险",
    bgVar: "--category-investment-bg",
    borderVar: "--category-investment",
    desc: "兼具理财属性的保险产品，如增额终身寿、年金险（理财型）。"
  }
];

const assetTypeMap: Record<
  string,
  { key: string; icon: string; label: string; color: string }[]
> = {
  cash: [
    {
      key: "bank",
      icon: "ep:bank",
      label: "活期/余额宝",
      color: "var(--add-type-cash)"
    },
    {
      key: "money_fund",
      icon: "ep:money",
      label: "货币基金",
      color: "var(--add-type-money-fund)"
    },
    {
      key: "cash_other",
      icon: "ep:wallet",
      label: "其他现金",
      color: "var(--add-type-cash-other)"
    }
  ],
  investment: [
    {
      key: "stock",
      icon: "ep:trend-charts",
      label: "股票",
      color: "var(--invest-stock)"
    },
    {
      key: "fund",
      icon: "ep:money",
      label: "基金",
      color: "var(--invest-fund)"
    },
    {
      key: "bond",
      icon: "ep:document",
      label: "可转债",
      color: "var(--invest-bond)"
    },
    {
      key: "etf",
      icon: "ep:pie-chart",
      label: "ETF",
      color: "var(--invest-etf)"
    },
    {
      key: "crypto",
      icon: "ep:coin",
      label: "虚拟货币",
      color: "var(--invest-crypto)"
    },
    {
      key: "saving",
      icon: "ep:bank",
      label: "定期/理财",
      color: "var(--invest-saving)"
    }
  ],
  fixed: [
    {
      key: "house",
      icon: "ep:house",
      label: "房产",
      color: "var(--add-type-house)"
    },
    { key: "car", icon: "ep:van", label: "汽车", color: "var(--add-type-car)" },
    {
      key: "gold",
      icon: "ep:medal",
      label: "黄金",
      color: "var(--add-type-gold)"
    }
  ],
  receivable: [
    {
      key: "personal_loan",
      icon: "ep:user",
      label: "个人借款",
      color: "var(--add-type-personal-loan)"
    },
    {
      key: "prepaid",
      icon: "ep:credit-card",
      label: "预付款",
      color: "var(--add-type-prepaid)"
    }
  ],
  liability: [
    {
      key: "credit_card",
      icon: "ep:credit-card",
      label: "信用卡",
      color: "var(--add-type-credit-card)"
    },
    {
      key: "mortgage",
      icon: "ep:house",
      label: "房屋贷款",
      color: "var(--add-type-mortgage)"
    },
    {
      key: "car_loan",
      icon: "ep:van",
      label: "汽车贷款",
      color: "var(--add-type-car-loan)"
    }
  ],
  insurance: [
    {
      key: "life",
      icon: "ep:shield",
      label: "寿险",
      color: "var(--add-type-life)"
    },
    {
      key: "health",
      icon: "ep:first-aid-kit",
      label: "健康险",
      color: "var(--add-type-health)"
    },
    {
      key: "annuity",
      icon: "ep:document",
      label: "年金险",
      color: "var(--add-type-annuity)"
    }
  ]
};

const activeCategory = ref("investment");
const allAssets = ref<any[]>([]);
// 投资明细分页数据（后端分页；market_value/pnl 后端暂不产出，见 Position 类型注释的已知 bug）
const investmentPositions = ref<Position[]>([]);
const investmentTotal = ref(0);
const distributions = ref<any>(null);
const investmentGroupsRaw = ref<any[]>([]);
const loading = ref(false);
const investmentPage = ref(1);
const pageSize = 10;
const investmentLoading = ref(false);

// 🔥 新增：汇总缓存与按需加载数据源
const assetsSummary = ref<Record<string, number>>({});
const assetCache = ref<Record<string, any[]>>({});
const currentAssets = ref<any[]>([]);

const editAssetDialogVisible = ref(false);
const savingAsset = ref(false);
const editAssetForm = ref<{ id: number | null; amount: number; notes: string }>(
  {
    id: null,
    amount: 0,
    notes: ""
  }
);

const getCategoryTabStyle = (key: string) => {
  const isActive = activeCategory.value === key;
  const cat = categories.find(c => c.key === key);
  if (!cat) return {};
  if (isActive) {
    return {
      backgroundColor: `var(${cat.bgVar})`,
      borderColor: `var(${cat.borderVar})`,
      boxShadow: "var(--shadow-raised)"
    };
  }
  return {};
};

const getAllocLabel = (key: string | null): string => {
  if (!key) return "未配置";
  const opt = ALLOCATION_OPTIONS.find(item => item.value === key);
  return opt ? opt.label : key;
};

const getAllocColor = (key: string | null): string => {
  const colorMap: Record<string, string> = {
    liquid: "var(--sankey-liquid)",
    stable: "var(--sankey-stable)",
    longterm: "var(--sankey-longterm)",
    speculative: "var(--sankey-speculative)",
    security: "var(--sankey-security)"
  };
  return colorMap[key || ""] || "var(--text-primary)";
};

const getAllocBgColor = (key: string | null): string => {
  return getColorWithAlpha(getAllocColor(key), 0.15);
};

const getMajorCategoryLabel = (key: string) => {
  const cat = categories.find(c => c.key === key);
  return cat ? cat.label : key;
};

const activeCategoryDesc = computed(
  () => categories.find(c => c.key === activeCategory.value)?.desc || ""
);

const activeAssetTypes = computed(
  () => assetTypeMap[activeCategory.value] || []
);

// 投资分布：消费后端 GET /api/summary/groups/?dimension=type（含 count/总市值），
// 按原页面语义合并「股票+可转债→证券」「基金→场外基金」
const investmentGroups = computed(() => {
  if (activeCategory.value !== "investment") return [];

  const typeMetaMap: Record<
    string,
    { label: string; icon: string; color: string }
  > = {
    securities: {
      label: "股票",
      icon: "ep:trend-charts",
      color: "var(--invest-stock)"
    },
    fund: { label: "基金", icon: "ep:money", color: "var(--invest-fund)" }
  };
  // 后端 type_label → 页面分组 key（股票/可转债合并为证券，基金归基金，其余忽略）
  const groupKeyMap: Record<string, string> = {
    股票: "securities",
    可转债: "securities",
    基金: "fund"
  };

  const groups: Record<string, { total: number; count: number }> = {};
  for (const g of investmentGroupsRaw.value) {
    const key = groupKeyMap[g.name];
    if (!key) continue;
    if (!groups[key]) groups[key] = { total: 0, count: 0 };
    groups[key].total += g.total || 0;
    groups[key].count += g.count || 0;
  }

  return Object.entries(groups).map(([type, data]) => {
    const meta = typeMetaMap[type];
    return {
      type,
      label: meta?.label || type,
      icon: meta?.icon || "ep:question",
      color: meta?.color || "var(--color-neutral)",
      ...data
    };
  });
});

const resolveCSSVar = (varName: string): string => {
  const name = varName.replace(/var\(|\)/g, "").trim();
  return getCssVar(name, "#8E8B82");
};

const getColorWithAlpha = (colorVar: string, alpha: number): string => {
  const hex = resolveCSSVar(colorVar);
  if (!/^#[0-9a-fA-F]{3,8}$/.test(hex)) return `rgba(0,0,0,${alpha})`;
  let r = 0,
    g = 0,
    b = 0;
  if (hex.length === 4) {
    r = parseInt(hex[1] + hex[1], 16);
    g = parseInt(hex[2] + hex[2], 16);
    b = parseInt(hex[3] + hex[3], 16);
  } else {
    r = parseInt(hex.slice(1, 3), 16);
    g = parseInt(hex.slice(3, 5), 16);
    b = parseInt(hex.slice(5, 7), 16);
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

// 🔥 优化：不再遍历全量列表，只读汇总接口的数据
const getCategoryTotal = (key: string): number => {
  if (key === "investment") {
    // 持仓市值总额走后端 distributions（含汇率换算），不再遍历全量明细
    return distributions.value?.positions_total_mv || 0;
  }
  return assetsSummary.value[key] || 0;
};

// 投资明细：后端真实分页拉取（对齐分页信封 { data: Position[], total, page, per_page, message }）
async function loadInvestmentPage(page: number) {
  investmentLoading.value = true;
  try {
    const res = await getPositions({ page, per_page: pageSize });
    investmentPositions.value = res?.data ?? [];
    investmentTotal.value = res?.total ?? investmentPositions.value.length;
  } catch (e) {
    console.error("加载投资明细分页失败", e);
    investmentPositions.value = [];
  } finally {
    investmentLoading.value = false;
  }
}

// 🔥 优化：按需加载该大类的具体资产数据
const loadCategoryAssets = async (category: string) => {
  if (category === "investment") {
    currentAssets.value = [];
    return;
  }
  if (assetCache.value[category]) {
    currentAssets.value = assetCache.value[category];
    return;
  }
  try {
    const res = await getAssets({ major_category: category, per_page: 500 });
    const items = (res as any)?.data ?? [];
    assetCache.value[category] = items;
    currentAssets.value = items;
  } catch (e) {
    console.error("加载分类资产失败", e);
  }
};

watch(activeCategory, newVal => {
  loadCategoryAssets(newVal);
});

watch(activeCategory, () => {
  investmentPage.value = 1;
});

function handleAddType(typeKey: string) {
  router.push(
    `/asset/asset-entry?category=${activeCategory.value}&type=${typeKey}`
  );
}

function openEditAssetDialog(row: any) {
  editAssetForm.value = {
    id: row.id,
    amount: row.amount || 0,
    notes: row.notes || ""
  };
  editAssetDialogVisible.value = true;
}

async function saveAssetEdit() {
  if (!editAssetForm.value.id) return;
  savingAsset.value = true;
  try {
    await updateAsset(editAssetForm.value.id, {
      amount: editAssetForm.value.amount,
      notes: editAssetForm.value.notes
    });
    ElMessage.success("资产已更新");
    editAssetDialogVisible.value = false;
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.message || "更新失败");
  } finally {
    savingAsset.value = false;
  }
}

async function confirmDeleteAsset(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定要删除资产「${row.name}」吗？此操作不可恢复。`,
      "删除确认",
      {
        confirmButtonText: "确认删除",
        cancelButtonText: "取消",
        type: "warning"
      }
    );
    await deleteAsset(row.id);
    ElMessage.success("资产已删除");
    await fetchData();
  } catch (e: any) {
    if (e !== "cancel") {
      ElMessage.error(e?.message || "删除失败");
    }
  }
}

// 🔥 全新 fetchData：只请求基础汇总、分布与投资分组接口
async function fetchData() {
  loading.value = true;
  try {
    const [summaryRes, distRes, groupsRes] = await Promise.all([
      getAssetsSummary(),
      getDistributions(),
      getPositionGroups("type")
    ]);

    // 汇总数据直接赋值
    // 🔥 核心修复：同时兼容后端返回的【数组格式】和【旧对象格式】
    const summaryData = (summaryRes as any)?.data ?? {};
    let summaryDict = {};

    if (Array.isArray(summaryData)) {
      // 情况1：如果后端返回的是数组（[{code, value}, ...]）
      summaryData.forEach(item => {
        summaryDict[item.code] = item.value;
      });
    } else {
      // 情况2：如果后端返回的还是旧的对象（{ cash: 0, fixed: ... }）
      summaryDict = summaryData;
    }
    assetsSummary.value = summaryDict;

    const distData = (distRes as any)?.data;
    distributions.value =
      distData && typeof distData === "object" ? distData : null;

    const groupsData = (groupsRes as any)?.data;
    investmentGroupsRaw.value = Array.isArray(groupsData)
      ? groupsData
      : groupsData?.data || [];

    await loadInvestmentPage(investmentPage.value);

    if (activeCategory.value !== "investment") {
      await loadCategoryAssets(activeCategory.value);
    }
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}

// 投资明细分页切换时重新拉取
watch(investmentPage, page => {
  loadInvestmentPage(page);
});

// 账户/持仓数据变更后全局自动刷新
usePageRefresh(() => {
  fetchData();
});

onMounted(() => {
  const tab = route.query.tab as string;
  if (tab && categories.some(c => c.key === tab)) {
    activeCategory.value = tab;
  }
  fetchData();
});
</script>

<style scoped>
/* 分类标签栏：标准圆角，非胶囊 */
.category-tab {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  min-height: 80px;
  padding: 14px 16px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-raised);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.category-tab:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.category-tab.active {
  border-width: 2px;
}

.category-tab-label {
  font-size: 14px;
  color: inherit;
}

.category-tab-amount {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.category-tab-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
  font-size: 16px;
  color: var(--text-tertiary);
}

/* 统一卡片样式（投资分布 & 快捷操作共用） */
.summary-card-item {
  transition: all 0.2s ease;
}

.summary-card-item:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-2px);
}

.summary-card-item:active {
  transform: scale(0.98);
}

/* 表格行高增加，提升呼吸感 */
:deep(.el-table__body td) {
  padding-top: 14px;
  padding-bottom: 14px;
}

:deep(.el-table__header th) {
  padding-top: 12px;
  padding-bottom: 12px;
}

:deep(.el-table td) {
  border-bottom-color: var(--border-light);
}

:deep(.el-table__body tr:hover > td) {
  background-color: var(--bg-hover) !important;
}
</style>
