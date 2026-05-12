<!-- src/components/QuickEntry/TransactionModal.vue -->
<template>
  <el-dialog
    v-model="visible"
    title="📝 记录一笔交易"
    width="580px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="resetForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="90px"
      size="default"
    >
      <!-- 1. 产品类型 (仅在买入/存入时显示) -->
      <template v-if="isBuyLike">
        <el-form-item label="产品类型" prop="type">
          <el-select v-model="form.type" class="w-full" @change="onTypeChange">
            <el-option label="🏠 通用资产/负债" value="generic" />
            <el-option label="📈 股票" value="stock" />
            <el-option label="📊 场外基金" value="fund" />
            <el-option label="₿ 虚拟货币" value="crypto" />
            <el-option label="📜 可转债" value="bond" />
            <el-option label="🏦 银行理财/存款" value="saving" />
            <el-option label="🏠 其他静态资产" value="static" />
          </el-select>
        </el-form-item>

        <!-- 动态字段区域（根据产品类型变化） -->
        <!-- 通用资产/负债 -->
        <template v-if="form.type === 'generic'">
          <!-- 大类选择 -->
          <el-form-item label="资产大类" prop="majorCategory">
            <el-select v-model="form.majorCategory" class="w-full" @change="onMajorCategoryChange">
              <el-option
                v-for="cat in majorCategoryOptions"
                :key="cat.value"
                :label="cat.label"
                :value="cat.value"
              />
            </el-select>
          </el-form-item>

          <!-- 负债专用：小类选择 -->
          <el-form-item v-if="form.majorCategory === 'liability'" label="负债类别">
            <el-select v-model="form.minorCategory" class="w-full" filterable allow-create>
              <el-option label="信用卡" value="信用卡" />
              <el-option label="花呗" value="花呗" />
              <el-option label="京东白条" value="京东白条" />
              <el-option label="房屋贷款" value="房屋贷款" />
              <el-option label="汽车贷款" value="汽车贷款" />
              <el-option label="网贷" value="网贷" />
              <el-option label="个人借款" value="个人借款" />
              <el-option label="自定义负债" value="其他负债" />
            </el-select>
          </el-form-item>

          <!-- 固定资产小类 -->
          <el-form-item v-if="form.majorCategory === 'fixed'" label="资产类型">
            <el-select v-model="form.minorCategory" class="w-full" filterable allow-create>
              <el-option label="房产" value="房产" />
              <el-option label="汽车" value="汽车" />
              <el-option label="黄金" value="黄金" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>

          <!-- 通用字段 -->
          <el-form-item label="名称" prop="name">
            <el-input v-model="form.name" placeholder="如：招商银行房贷" />
          </el-form-item>
          <el-form-item label="金额/估值" prop="amount">
            <el-input-number v-model="form.amount" :min="0" :precision="2" class="w-full" />
          </el-form-item>
          <el-form-item label="所属账户">
            <el-input v-model="form.account_name" placeholder="如：招商银行" />
          </el-form-item>
        </template>

        <!-- 股票、可转债：远程搜索 -->
        <template v-if="['stock', 'bond'].includes(form.type)">
          <el-form-item label="证券" prop="symbol">
            <el-select
              v-model="selectedSecurityOption"
              value-key="symbol"
              remote
              filterable
              reserve-keyword
              placeholder="输入代码或名称搜索"
              :remote-method="remoteSearch"
              :loading="searchLoading"
              @change="onSecuritySelected"
              clearable
              class="w-full"
            >
              <el-option
                v-for="item in securityOptions"
                :key="item.symbol"
                :label="`${item.symbol} ${item.name}`"
                :value="item"
              />
            </el-select>
          </el-form-item>
          <el-form-item prop="name" v-show="false">
            <el-input v-model="form.name" />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="数量(股/张)" prop="quantity">
                <el-input-number
                  v-model="form.quantity"
                  :min="0"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="成交单价" prop="price">
                <el-input-number
                  v-model="form.price"
                  :min="0"
                  :precision="2"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- 场外基金：远程搜索 -->
        <template v-if="form.type === 'fund'">
          <el-form-item label="基金" prop="symbol">
            <el-select
              v-model="selectedSecurityOption"
              value-key="symbol"
              remote
              filterable
              reserve-keyword
              placeholder="输入代码或名称搜索"
              :remote-method="remoteSearch"
              :loading="searchLoading"
              @change="onSecuritySelected"
              clearable
              class="w-full"
            >
              <el-option
                v-for="item in securityOptions"
                :key="item.symbol"
                :label="`${item.symbol} ${item.name}`"
                :value="item"
              />
            </el-select>
          </el-form-item>
          <el-form-item prop="name" v-show="false">
            <el-input v-model="form.name" />
          </el-form-item>
          <el-form-item label="申购时间">
            <el-switch
              v-model="form.isAfter15"
              active-text="15:00之后"
              inactive-text="15:00之前"
              :active-value="true"
              :inactive-value="false"
            />
            <span class="text-xs text-gray-400 ml-2">
              {{ form.isAfter15 ? "按下一交易日净值确认" : "按当日净值确认" }}
            </span>
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="申购份额" prop="quantity">
                <el-input-number
                  v-model="form.quantity"
                  :min="0"
                  :precision="2"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="单位净值" prop="price">
                <el-input-number
                  v-model="form.price"
                  :min="0"
                  :precision="4"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- 虚拟货币 -->
        <template v-if="form.type === 'crypto'">
          <el-form-item label="币种" prop="symbol">
            <el-input v-model="form.symbol" placeholder="BTC" />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="数量(枚)" prop="quantity">
                <el-input-number
                  v-model="form.quantity"
                  :min="0"
                  :precision="6"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="成交价(USD)" prop="price">
                <el-input-number
                  v-model="form.price"
                  :min="0"
                  :precision="2"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- 银行理财/存款 -->
        <template v-if="form.type === 'saving'">
          <el-form-item label="产品名称" prop="name">
            <el-input v-model="form.name" placeholder="如 招商银行朝朝宝" />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="本金(元)" prop="quantity">
                <el-input-number
                  v-model="form.quantity"
                  :min="0"
                  :precision="2"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="年化利率(%)" prop="interestRate">
                <el-input-number
                  v-model="form.interestRate"
                  :min="0"
                  :precision="2"
                  class="w-full"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- 其他静态资产 -->
        <template v-if="form.type === 'static'">
          <el-form-item label="资产名称" prop="name">
            <el-input v-model="form.name" placeholder="如 招商银行活期" />
          </el-form-item>
          <el-form-item label="当前估值(元)" prop="quantity">
            <el-input-number
              v-model="form.quantity"
              :min="0"
              :precision="2"
              class="w-full"
            />
          </el-form-item>
        </template>
      </template>

      <!-- 2. 操作类型 -->
      <el-form-item label="操作类型" prop="opType">
        <el-radio-group v-model="form.opType">
          <el-radio-button
            v-for="opt in currentOpTypeOptions"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </el-radio-button>
        </el-radio-group>
      </el-form-item>

      <!-- 3. 卖出/分红/取出专用区域 -->
      <template v-if="isSellLike">
        <!-- 选择账户 -->
        <el-form-item label="选择账户" prop="account_name">
          <el-select
            v-model="form.account_name"
            class="w-full"
            placeholder="选择要操作的账户"
            @change="onAccountChange"
          >
            <el-option
              v-for="acc in availableAccounts"
              :key="acc"
              :label="acc"
              :value="acc"
            />
          </el-select>
          <div
            v-if="!availableAccounts.length"
            class="text-gray-400 text-xs mt-1"
          >
            暂无拥有持仓的账户
          </div>
        </el-form-item>

        <!-- 选择持仓 -->
        <el-form-item
          v-if="form.account_name"
          label="选择持仓"
          prop="positionId"
        >
          <el-select
            v-model="form.positionId"
            class="w-full"
            filterable
            placeholder="选择资产"
            @change="onPositionSelect"
          >
            <el-option
              v-for="pos in accountPositions"
              :key="pos.id"
              :label="`${pos.name || pos.symbol} (可卖 ${pos.quantity})`"
              :value="pos.id"
            />
          </el-select>
        </el-form-item>

        <!-- 卖出/取出数量区 -->
        <template
          v-if="['sell', 'withdraw'].includes(form.opType) && form.positionId"
        >
          <el-form-item label="操作数量">
            <el-input-number
              v-model="form.quantity"
              :min="1"
              :max="selectedPosition?.quantity ?? 1"
              :step="getLotSize(form.market || 'CN_A')"
              class="w-full"
            />
            <span class="text-xs text-gray-400 mt-1">
              可卖 {{ selectedPosition?.quantity ?? 0 }}，最低一手
              {{ getLotSize(form.market || "CN_A") }} 股/张
              <span v-if="isOddLot" class="text-orange-500"
                >（含碎股，可全部卖出）</span
              >
            </span>
          </el-form-item>
          <el-form-item label="快捷操作">
            <el-button-group>
              <el-button
                v-for="ratio in quickRatios"
                :key="ratio.label"
                size="small"
                @click="applyQuickRatio(ratio.value)"
              >
                {{ ratio.label }}
              </el-button>
            </el-button-group>
          </el-form-item>
          <el-form-item label="操作价格">
            <el-input-number
              v-model="form.price"
              :min="0"
              :precision="2"
              class="w-full"
              placeholder="卖出/取出价格"
            />
            <span class="text-xs text-gray-400"
              >默认为成本价，可按实际成交价修改</span
            >
          </el-form-item>
        </template>

        <!-- 基金转换提示（仅基金卖出） -->
        <el-form-item
          v-if="form.opType === 'sell' && selectedPosition?.type === 'fund'"
        >
          <el-alert
            title="基金转换"
            type="info"
            :closable="false"
            show-icon
            description="转换功能即将推出，届时可卖出基金的同时买入另一只基金。"
          />
        </el-form-item>
      </template>

      <!-- 4. 通用字段（卖出/分红/取出时不显示，因为已通过"选择账户"确定） -->
      <el-form-item v-if="!isSellLike" label="所属账户" prop="account_name">
        <el-select
          v-model="form.account_name"
          class="w-full"
          filterable
          allow-create
          placeholder="选择或输入账户"
        >
          <el-option label="华泰证券" value="华泰证券" />
          <el-option label="富途证券" value="富途证券" />
          <el-option label="支付宝基金" value="支付宝基金" />
          <el-option label="天天基金" value="天天基金" />
          <el-option label="招商银行" value="招商银行" />
        </el-select>
      </el-form-item>

      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="交易日期" prop="purchase_date">
            <el-date-picker
              v-model="form.purchase_date"
              type="date"
              class="w-full"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="手续费" prop="fee">
            <el-input-number
              v-model="form.fee"
              :min="0"
              :precision="2"
              class="w-full"
              placeholder="0.00"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 配置目标（仅买入/存入时显示） -->
      <el-form-item v-if="isBuyLike" label="配置目标" prop="allocation">
        <el-radio-group v-model="form.allocation" class="allocation-group">
          <el-radio-button value="liquid">💧 活钱</el-radio-button>
          <el-radio-button value="stable">🛡️ 稳健底仓</el-radio-button>
          <el-radio-button value="longterm">📈 长期增值</el-radio-button>
          <el-radio-button value="speculative">⚡ 高风险博弈</el-radio-button>
          <el-radio-button value="security">🛟 保险保障</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <!-- 预估金额 -->
      <el-form-item label="预估金额">
        <el-input :value="estimatedAmount" disabled>
          <template #append>元</template>
        </el-input>
      </el-form-item>

      <!-- 备注 -->
      <el-form-item label="投资手记">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          placeholder="如：定投第一期、低位补仓"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        确认记账
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { createPosition } from "@/api/positions";
import { createAsset } from "@/api/assets";
import { http } from "@/utils/http";
import type { FormInstance, FormRules } from "element-plus";
import { searchSecurities } from "@/api/securities";
import { searchFunds } from "@/api/funds";

// ── 常量 ──
const LOT_SIZE: Record<string, number> = {
  CN_A: 100, // A股一手100股
  CN_HK: 100, // 港股默认一手100股（实际因股而异，MVP先统一）
  US: 1, // 美股1股
  CRYPTO: 1, // 虚拟货币
  default: 1 // 基金、其他
};

// 快捷比例
const quickRatios = [
  { label: "1/4", value: 1 / 4 },
  { label: "1/3", value: 1 / 3 },
  { label: "1/2", value: 1 / 2 },
  { label: "3/4", value: 3 / 4 },
  { label: "全部", value: 1 }
];

const majorCategoryOptions = [
  { label: '💵 流动资金', value: 'cash' },
  { label: '🏠 固定资产', value: 'fixed' },
  { label: '📈 投资理财', value: 'investment' },
  { label: '🤝 应收款', value: 'receivable' },
  { label: '📉 负债', value: 'liability' },
  { label: '🛡️ 保险', value: 'insurance' },
];

// ── 表单默认值 ──
const defaultForm = () => ({
  majorCategory: 'fixed',
  minorCategory: '',
  amount: 0,
  type: "stock",
  opType: "buy",
  positionId: null as number | null,
  market: "CN_A",
  currency: "CNY",
  symbol: "",
  name: "",
  quantity: 0,
  price: 0,
  account_name: "华泰证券",
  purchase_date: new Date().toISOString().slice(0, 10),
  fee: 0,
  isAfter15: false,
  interestRate: 0,
  allocation: "longterm",
  notes: ""
});

const form = reactive(defaultForm());

// ── 远程搜索状态 ──
const searchLoading = ref(false);
const securityOptions = ref<any[]>([]);
const selectedSecurityOption = ref<any>(null);

// ── 状态 ──
const positionsByAccount = ref<Record<string, any[]>>({});
const selectedPosition = ref<any>(null);
const formRef = ref<FormInstance>();
const submitting = ref(false);

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

// ── 辅助计算 ──
const isBuyLike = computed(
  () =>
    ["buy", "deposit"].includes(form.opType) &&
    !["sell", "dividend", "withdraw"].includes(form.opType)
);
const isSellLike = computed(() =>
  ["sell", "dividend", "withdraw"].includes(form.opType)
);

const availableAccounts = computed(() => Object.keys(positionsByAccount.value));

const accountPositions = computed(() => {
  if (!form.account_name) return [];
  return positionsByAccount.value[form.account_name] || [];
});

const isOddLot = computed(() => {
  const total = selectedPosition.value?.quantity ?? 0;
  const lot = getLotSize(form.market || "CN_A");
  return total % lot !== 0 && total < lot;
});

const estimatedAmount = computed(() => {
  if (form.type === "static" || form.type === "saving")
    return form.quantity.toFixed(2);
  return (form.quantity * form.price).toFixed(2);
});

// ── 动态操作类型 ──
const opTypeMap: Record<string, { label: string; value: string }[]> = {
  stock: [
    { label: "买入", value: "buy" },
    { label: "卖出", value: "sell" },
    { label: "分红", value: "dividend" },
    { label: "转入", value: "deposit" },
    { label: "转出", value: "withdraw" }
  ],
  fund: [
    { label: "申购", value: "buy" },
    { label: "赎回", value: "sell" },
    { label: "分红", value: "dividend" },
    { label: "转换", value: "transfer" }
  ],
  crypto: [
    { label: "买入", value: "buy" },
    { label: "卖出", value: "sell" }
  ],
  bond: [
    { label: "买入", value: "buy" },
    { label: "卖出", value: "sell" },
    { label: "分红", value: "dividend" }
  ],
  saving: [
    { label: "存入", value: "deposit" },
    { label: "取出", value: "withdraw" }
  ],
  static: [
    { label: "新增", value: "deposit" },
    { label: "移除", value: "withdraw" }
  ]
};

const currentOpTypeOptions = computed(() => {
  return opTypeMap[form.type] || [{ label: "买入", value: "buy" }];
});

function onMajorCategoryChange() {
  form.minorCategory = ''
}

function getLotSize(market: string): number {
  if (form.type === "bond") return 10;
  return LOT_SIZE[market] || LOT_SIZE.default;
}

function applyQuickRatio(ratio: number) {
  const total = selectedPosition.value?.quantity ?? 0;
  const lot = getLotSize(form.market || "CN_A");
  let target = Math.floor((total * ratio) / lot) * lot;
  if (ratio === 1) target = total;
  if (target <= 0) target = lot;
  form.quantity = target;
}

// ── 远程搜索 ──
const remoteSearch = async (query: string) => {
  if (!query) {
    securityOptions.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    if (form.type === 'fund') {
      const res = await searchFunds(query);
      const dataArr = Array.isArray(res) ? res : (res as any)?.data ?? [];
      securityOptions.value = dataArr.map((f: any) => ({
        symbol: f.code,
        name: f.name,
        market: 'CN_A',
        type: 'fund'
      }));
    } else if (['stock', 'bond'].includes(form.type)) {
      const res = await searchSecurities(query);
      const dataArr = Array.isArray(res) ? res : (res as any)?.data ?? [];
      securityOptions.value = dataArr.map((s: any) => ({
        symbol: s.symbol,
        name: s.name,
        market: s.market,
        type: s.type
      }));
    } else {
      securityOptions.value = [];
    }
  } catch (e) {
    ElMessage.error('搜索失败');
  } finally {
    searchLoading.value = false;
  }
};

// 选中后填充表单
const onSecuritySelected = (option: any) => {
  if (!option) {
    form.symbol = '';
    form.name = '';
    form.market = 'CN_A';
    return;
  }
  form.symbol = option.symbol;
  form.name = option.name;
  form.market = option.market;
  if (option.market === 'CN_HK') form.currency = 'HKD';
  else if (option.market === 'US') form.currency = 'USD';
  else form.currency = 'CNY';
  // 不修改 form.type，保持用户已选的产品类型
};

// ── 数据获取 ──
async function fetchPositionsByAccount() {
  try {
    const res = await http.request<any>(
      "get",
      "/api/positions?group_by=account"
    );
    positionsByAccount.value = (res as any)?.data ?? res ?? {};
  } catch {
    positionsByAccount.value = {};
  }
}

function onAccountChange() {
  form.positionId = null;
  selectedPosition.value = null;
}

function onPositionSelect(positionId: number) {
  const pos = accountPositions.value.find((p: any) => p.id === positionId);
  if (!pos) return;
  selectedPosition.value = pos;
  form.symbol = pos.symbol;
  form.name = pos.name;
  form.market = pos.market;
  form.currency = pos.currency;
  form.quantity = pos.quantity; // 默认全卖
  form.price = pos.current_price ?? pos.avg_price; // 卖出价格默认当前价或成本价
}

function onTypeChange() {
  // 清空原有字段
  form.symbol = "";
  form.name = "";
  form.quantity = 0;
  form.price = 0;
  form.isAfter15 = false;
  form.interestRate = 0;
  form.opType = currentOpTypeOptions.value[0]?.value ?? "buy";
  // 清空远程搜索状态
  securityOptions.value = [];
  selectedSecurityOption.value = null;
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedPosition.value = null;
  positionsByAccount.value = {};
  securityOptions.value = [];
  selectedSecurityOption.value = null;
  formRef.value?.resetFields();
}

// ── 校验规则 ──
const rules = computed<FormRules>(() => {
  const base: FormRules = {
    opType: [{ required: true, message: "请选择操作类型", trigger: "change" }],
    account_name: [
      { required: true, message: "请选择账户", trigger: "change" }
    ],
    purchase_date: [
      { required: true, message: "请选择日期", trigger: "change" }
    ]
  };

  if (isBuyLike.value) {
    base.type = [
      { required: true, message: "请选择产品类型", trigger: "change" }
    ];
    // 对于远程搜索的类型，不再强制 name 必填，因为搜索后会自动填充
    if (!['stock', 'bond', 'fund'].includes(form.type)) {
      if (form.type !== "static" && form.type !== "saving") {
        base.symbol = [
          { required: true, message: "请输入代码", trigger: "blur" }
        ];
        base.name = [{ required: true, message: "请输入名称", trigger: "blur" }];
        base.quantity = [
          { required: true, message: "请输入数量", trigger: "blur" }
        ];
        base.price = [{ required: true, message: "请输入价格", trigger: "blur" }];
      }
    } else {
      // 远程搜索类型：symbol 仍然必填（选择后会填）
      base.symbol = [
        { required: true, message: "请搜索并选择产品", trigger: "change" }
      ];
      // name 被选择后自动填充，保留验证但可以通过隐藏的 input 实现（已在模板中添加）
      base.name = [{ required: true, message: "产品名称不可为空", trigger: "blur" }];
      base.quantity = [
        { required: true, message: "请输入数量", trigger: "blur" }
      ];
      base.price = [{ required: true, message: "请输入价格", trigger: "blur" }];
    }
  }

  if (isSellLike.value) {
    base.positionId = [
      { required: true, message: "请选择要操作的持仓", trigger: "change" }
    ];
    if (["sell", "withdraw"].includes(form.opType)) {
      base.quantity = [
        { required: true, message: "请输入操作数量", trigger: "blur" }
      ];
    }
  }

  return base;
});

// ── 提交 ──
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (form.type === 'generic') {
      // 通用资产/负债
      const body = {
        major_category: form.majorCategory,
        minor_category: form.minorCategory || null,
        name: form.name,
        amount: form.amount,
        currency: 'CNY',
        account_name: form.account_name,
        allocation: form.allocation,
        notes: form.notes,
        start_date: form.purchase_date,
      }
      await createAsset(body)
      ElMessage.success('资产已记录')
      visible.value = false
      emit('submitted')
      return
    }

    // 交易性资产（股票/基金/虚拟币等）
    const body: any = {
      symbol: form.symbol || "manual",
      name: form.name || form.symbol || form.type,
      op_type: form.opType,
      position_id: form.positionId,
      market: form.type === "crypto" ? "CRYPTO" : form.market,
      type: form.type === "saving" ? "saving" : form.type,
      account_name: form.account_name,
      quantity: form.type === "static" ? 1 : form.quantity,
      avg_price: form.type === "static" ? form.quantity : form.price,
      currency: form.currency || (form.type === "crypto" ? "USD" : "CNY"),
      purchase_date: form.purchase_date,
      fee: form.fee,
      notes: form.notes,
      allocation: form.allocation,
      isAfter15: form.isAfter15,
      interestRate: form.interestRate
    }

    await createPosition(body)
    ElMessage.success("记账成功！")
    visible.value = false
    emit("submitted")
  } catch (e: any) {
    ElMessage.error(e?.message || "记账失败")
  } finally {
    submitting.value = false
  }
}

// 监听操作类型变化
watch([() => form.opType, () => form.type], ([newOp]) => {
  if (isSellLike.value) {
    fetchPositionsByAccount();
  } else {
    // 买入时重置卖出相关状态
    selectedPosition.value = null;
    positionsByAccount.value = {};
  }
});

// 初始化操作类型
watch(
  () => form.type,
  () => {
    onTypeChange();
  },
  { immediate: true }
);
</script>

<style scoped>
.allocation-group {
  flex-wrap: wrap;
}

.el-radio-button {
  margin-bottom: 4px;
}
</style>
