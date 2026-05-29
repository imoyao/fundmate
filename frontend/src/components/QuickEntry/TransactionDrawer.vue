<!-- src/components/QuickEntry/TransactionDrawer.vue -->
<template>
  <el-drawer
    v-model="visible"
    size="480px"
    direction="rtl"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="resetForm"
  >

    <template #header>
      <div class="flex items-center justify-between w-full">
        <span>记录交易</span>
        <el-button type="text" size="small" @click="goToInventory" class="text-gray-400 hover:text-primary">
          去「全面盘点」>
        </el-button>
      </div>
    </template>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="90px"
      size="large"
    >
      <!-- 操作类型切换 -->
      <el-form-item label="操作" prop="opType">
        <el-radio-group v-model="form.opType" @change="onOpTypeChange">
          <el-radio-button value="buy">买入</el-radio-button>
          <el-radio-button value="sell">卖出</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <!-- 买入时：产品信息已通过搜索获得，无需额外选择 -->
      <template v-if="form.opType === 'buy'">
        <el-form-item label="选择账户" prop="account_name">
          <div class="flex gap-2 w-full">
            <el-select
              v-model="form.account_name"
              class="flex-1"
              placeholder="选择交易账户"
              filterable
              :disabled="showQuickAddAccount"
            >
              <el-option
                v-for="ledger in ledgers"
                :key="ledger.id"
                :label="ledger.name"
                :value="ledger.name"
              />
            </el-select>
            <el-button
              v-if="!showQuickAddAccount"
              type="primary"
              text
              @click="showQuickAddAccount = true"
            >
              <IconifyIconOffline icon="ep:plus" />
            </el-button>
          </div>
          <div v-if="!ledgers.length && !showQuickAddAccount" class="text-gray-500 text-xs mt-1">
            暂无账户，点击右侧 + 按钮快速创建
          </div>

          <!-- 极简账户创建表单（内联展开） -->
          <div v-if="showQuickAddAccount" class="quick-add-account mt-3 p-3 border rounded-lg bg-gray-50">
            <el-input
              v-model="newAccountName"
              placeholder="输入账户名称，如：华泰证券"
              size="small"
              @keyup.enter="quickCreateAccount"
            />
            <div class="flex justify-end gap-2 mt-2">
              <el-button size="small" @click="showQuickAddAccount = false; newAccountName = ''">取消</el-button>
              <el-button
                size="small"
                type="primary"
                :loading="creatingAccount"
                :disabled="!newAccountName.trim()"
                @click="quickCreateAccount"
              >
                创建并选择
              </el-button>
            </div>
          </div>
        </el-form-item>
      </template>

      <!-- 卖出时：选择账户 → 选择持仓 -->
      <template v-if="form.opType === 'sell'">
        <el-form-item label="选择账户" prop="account_name">
          <el-select
            v-model="form.account_name"
            class="w-full"
            placeholder="选择交易账户"
            @change="onAccountChange"
          >
            <el-option
              v-for="acc in availableAccounts"
              :key="acc"
              :label="acc"
              :value="acc"
            />
          </el-select>
          <div v-if="!availableAccounts.length" class="text-gray-500 text-xs mt-1">
            暂无拥有持仓的账户
          </div>
        </el-form-item>

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

        <!-- 卖出数量/价格 -->
        <template v-if="form.positionId">
           <el-form-item label="卖出数量" prop="quantity">
            <div class="flex items-center gap-2 w-full">
              <el-input-number
                v-model="form.quantity"
                :min="getSellMin()"
                :max="selectedPosition?.quantity ?? 1"
                :step="getStepForSecurity()"
                :precision="getPrecisionForSecurity()"
                class="flex-1"
                :placeholder="`最低 ${getSellMin()} 股`"
              />
              <!-- 快捷操作 -->
              <el-button-group>
                <el-button
                  v-for="ratio in sellQuickRatios"
                  :key="ratio.label"
                  size="small"
                  @click="applySellQuickRatio(ratio.value)"
                >
                  {{ ratio.label }}
                </el-button>
              </el-button-group>
            </div>
            <span class="text-xs text-gray-500 mt-1">
              可卖 {{ selectedPosition?.quantity ?? 0 }}，最低卖出 {{ getSellMin() }} 股/张
              <span v-if="isOddLot" class="text-orange-500">（含碎股，可全部卖出）</span>
            </span>
          </el-form-item>

          <el-form-item label="卖出价格">
            <el-input-number
              v-model="form.price"
              :min="0"
              :step="0.01"
              :precision="2"
              class="w-full"
              placeholder="卖出价格"
            />
            <span class="text-xs text-gray-500">默认为成本价，可按实际成交价修改</span>
          </el-form-item>

          <!-- ⭐ 新增预估金额 -->
          <el-form-item label="预估金额">
            <el-input :model-value="(form.quantity * form.price).toFixed(2)" readonly disabled>
              <template #append>元</template>
            </el-input>
          </el-form-item>

        </template>
      </template>

      <!-- 买入时：证券搜索 -->
      <template v-if="form.opType === 'buy'">
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
              :label="`${item.symbol} ${item.name} (${item.type_label || item.type})`"
              :value="item"
            />
          </el-select>
          <div v-if="!securityOptions.length && !searchLoading" class="text-gray-500 text-xs mt-2">
            还没有持仓？去「全面盘点」导入交割单吧 >
          </div>
        </el-form-item>
      </template>

      <!-- 交易日期（通用） -->
      <el-form-item label="交易日期" prop="purchase_date">
        <el-date-picker
          v-model="form.purchase_date"
          type="date"
          class="w-full"
          value-format="YYYY-MM-DD"
        />
       <span v-if="isTradingDay === false" class="text-xs text-orange-500 mt-1">
         所选日期非交易日，请确认</span>
      </el-form-item>

      <!-- 场外基金确认日（仅基金且买入时显示） -->
      <el-form-item v-if="form.opType === 'buy' && selectedSecurityOption?.type === 'fund'" label="确认日">
        <el-input :model-value="confirmDate" disabled>
          <template #append>
            <el-tooltip content="净值将在确认日之后自动获取" placement="top">
              <IconifyIconOffline icon="ep:info-filled" class="text-gray-500" />
            </el-tooltip>
          </template>
        </el-input>
      </el-form-item>

      <!-- 成交价格（买入时必填） -->
      <el-form-item
        v-if="form.opType === 'buy'"
        :label="selectedSecurityOption?.type === 'fund' ? '单位净值' : '成交价格'"
        prop="price"
      >
        <el-input-number
          v-model="form.price"
          :min="0"
          :step="0.01"
          :precision="selectedSecurityOption?.type === 'fund' ? 4 : 2"
          class="w-full"
          :placeholder="selectedSecurityOption?.type === 'fund' ? '基金单位净值' : '每股/张成交价'"
        />
        <span class="text-xs text-gray-500 mt-1">
          <template v-if="selectedSecurityOption?.type === 'fund'">
            后期将自动获取基金净值，当前请手动输入
          </template>
          <template v-else>
            输入实际成交价，系统将根据金额自动计算份额（已扣除手续费）
          </template>
        </span>
      </el-form-item>

      <!-- 金额 / 份额切换 -->
      <el-form-item
         v-if="form.opType === 'buy'"
        :label="amountModeLabel"
         prop="amountOrQuantity">
        <div class="flex items-center gap-2">
          <el-input-number
            v-model="amountOrQuantity"
            :min="0"
            :step="amountMode === 'quantity' ? getStepForSecurity() : 0.01"
            :precision="amountMode === 'quantity' ? getPrecisionForSecurity() : 2"
            :controls="false"
            class="flex-1"
            :placeholder="amountMode === 'amount' ? '交易金额' : '交易份额'"
          />
          <el-button
            type="primary"
            text
            @click="toggleAmountMode"
            :disabled="!form.price || form.price <= 0"
          >
            <IconifyIconOffline icon="ep:switch" class="mr-1" />
            {{ amountMode === 'amount' ? '切换份额' : '切换金额' }}
          </el-button>
        </div>
        <!-- 份额辅助换算展示 -->
        <div v-if="form.price > 0" class="text-xs text-gray-500 mt-1">
          {{ amountMode === 'amount' ? `预估份额：约 ${computedQuantity.toFixed(2)} 份` : `预估金额：¥${computedAmount.toFixed(2)}` }}
        </div>
      </el-form-item>

      <!-- 费率 -->
      <el-form-item label="手续费" prop="fee" class="fee-form-item">
        <div class="flex items-center gap-2 w-full">
          <el-input-number
            v-model="form.fee"
            :controls="false"
            :min="0"
            :precision="2"
            class="flex-1"
            placeholder="0.00"
          />
          <el-select
            v-if="selectedSecurityOption?.type === 'fund' && form.opType === 'buy'"
            v-model="fundFeeDiscount"
            placeholder="折扣"
            size="small"
            style="width: 100px"
            @change="onFundFeeDiscountChange"
          >
            <el-option label="原价" :value="1.0" />
            <el-option label="1折" :value="0.1" />
            <el-option label="0.1折" :value="0.01" />
            <el-option label="免申购费" :value="0" />
          </el-select>
        </div>
        <span class="text-xs text-gray-500">费率已根据账户预设填充，可手动修改</span>
      </el-form-item>

      <!-- 预估结算 -->
      <el-form-item v-if="form.opType === 'buy'" label="预估金额" readonly disabled>
        <el-input :model-value="estimatedAmountDisplay" disabled>
          <template #append>元</template>
        </el-input>
      </el-form-item>

      <!-- 更多选项（折叠） -->
      <el-collapse v-model="activeCollapse" class="mt-2">
        <el-collapse-item  title="更多选项" name="more">
          <el-form-item label="配置目标" prop="allocation">
            <el-radio-group v-model="form.allocation">
              <el-radio-button v-for="opt in allocationOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="补充交易理由（选填）" />
          </el-form-item>
          <!-- 注意：下午3点前开关，合并到确认日计算中，此处不显示 -->
        </el-collapse-item>
      </el-collapse>

    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        确认记账
      </el-button>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createPosition } from "@/api/positions";
import type { FormInstance, FormRules } from "element-plus";
import { searchSecurities } from "@/api/securities";
import { searchFunds } from "@/api/funds";
import { getLedgers, createLedger as createLedgerApi } from "@/api/ledger";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getPositions } from "@/api/positions";
import { checkTradingDay, calcFundConfirmDate } from "@/api/utils";

const allocationOptions = [
  { value: 'liquid', label: '活钱' },
  { value: 'stable', label: '稳健底仓' },
  { value: 'longterm', label: '长期增值' },
  { value: 'speculative', label: '高风险博弈' },
  { value: 'security', label: '保险保障' },
];

// ── 表单数据 ──
const defaultForm = () => ({
  opType: 'buy' as 'buy' | 'sell',
  symbol: '',
  name: '',
  market: 'CN_A',
  type: 'stock',
  quantity: 0,
  price: 0,
  account_name: '',
  purchase_date: new Date().toISOString().slice(0, 10),
  confirm_date: '', // 基金确认日，由计算得来
  fee: 0,
  allocation: 'longterm',
  notes: '',
  positionId: null as number | null,
  isAfter15: false,
  interestRate: 0,
});

const form = reactive(defaultForm());
const formRef = ref<FormInstance>();
const submitting = ref(false);
// 极简账户创建
const showQuickAddAccount = ref(false);
const newAccountName = ref('');
const creatingAccount = ref(false);

const activeCollapse = ref<string[]>([]); // 控制折叠面板

// ── 搜索与证券选择 ──
const searchLoading = ref(false);
const securityOptions = ref<any[]>([]);
const selectedSecurityOption = ref<any>(null);

// 产品类型由搜索结果自动识别，不再需要手动选择

// ── 卖出相关状态 ──
const positionsByAccount = ref<Record<string, any[]>>({});
const selectedPosition = ref<any>(null);

// ── 账户列表 ──
const ledgers = ref<any[]>([]);

// ── 金额/份额模式 ──
const amountMode = ref<'amount' | 'quantity'>('amount');
const amountOrQuantity = ref(0); // 当前输入的值（金额或份额）

// ── 费率相关 ──
const fundFeeDiscount = ref(0.1); // 默认1折

// ── 全局常量 ──
const SEC_DEFAULTS = {
  subscription_rate: 0.015, // 默认基金申购费率
};

const isTradingDay = ref<boolean | null>(null);
const confirmDate = ref('');

// ── 辅助计算 ──
const isSellLike = computed(() => form.opType === 'sell');

const availableAccounts = computed(() => Object.keys(positionsByAccount.value));

const accountPositions = computed(() => {
  if (!form.account_name) return [];
  return positionsByAccount.value[form.account_name] || [];
});

// 修改后
const isOddLot = computed(() => {
  const total = selectedPosition.value?.quantity ?? 0;
  const step = getStepForSecurity();
  return total > 0 && total < step;
});

// 从金额或份额推算数量和价格
const computedQuantity = computed(() => {
  if (!form.price || form.price <= 0) return 0;
  if (amountMode.value === 'amount') {
    // 买入：份额 = (金额 - 手续费) / 价格
    const netAmount = Math.max(0, amountOrQuantity.value - form.fee);
    return netAmount / form.price;
  } else {
    return amountOrQuantity.value;
  }
});

const computedAmount = computed(() => {
  if (amountMode.value === 'quantity') {
    // 买入：金额 = 份额 × 价格 + 手续费
    return amountOrQuantity.value * form.price + form.fee;
  } else {
    return amountOrQuantity.value;
  }
});

const amountModeLabel = computed(() => amountMode.value === 'amount' ? '交易金额' : '交易份额');

const estimatedAmountDisplay = computed(() => {
  const amt = amountMode.value === 'amount' ? amountOrQuantity.value : computedAmount.value;
  return amt.toFixed(2);
});

// ── 动态获取账户费率并预填 ──
async function loadLedgers() {
  try {
    const res = await getLedgers();
    ledgers.value = res.data as any[] || [];
  } catch (e) { /* ignore */ }
}

function getAccountFeeConfig(accountName: string): any | null {
  const ledger = ledgers.value.find(l => l.name === accountName);
  if (!ledger || !ledger.fee_config) return null;
  try {
    return typeof ledger.fee_config === 'string' ? JSON.parse(ledger.fee_config) : ledger.fee_config;
  } catch {
    return null;
  }
}


async function fetchTradingDay() {
  if (form.opType !== 'buy' || selectedSecurityOption.value?.type === 'fund' || !form.purchase_date) {
    isTradingDay.value = null;
    return;
  }
  try {
    const res = await checkTradingDay(form.purchase_date);
    isTradingDay.value = (res as any)?.data?.is_trading_day ?? false;
  } catch {
    isTradingDay.value = null;
  }
}

async function fetchConfirmDate() {
  if (form.opType !== 'buy' || selectedSecurityOption.value?.type !== 'fund' || !form.purchase_date) {
    confirmDate.value = '';
    return;
  }
  try {
    const res = await calcFundConfirmDate({
      purchase_date: form.purchase_date,
      fund_type: 'domestic',
      is_after_15: form.isAfter15,
    });
    confirmDate.value = (res as any)?.data ?? '';
  } catch {
    confirmDate.value = '';
  }
}

// 最小交易单位（一手股数）
function getStepForSecurity(): number {
  // 场外基金始终按1份交易
  if (form.type === 'fund') return 1;

  const market = form.market || 'CN_A';
  // 美股、加密货币：1股起
  if (market === 'US' || market === 'CRYPTO') return 1;
  // 港股：一手股数因股而异，MVP暂定100股，后期从后端获取
  if (market === 'CN_HK') return 100;
  // 可转债：10张一手
  if (form.type === 'bond') return 10;

  // A股各板块
  if (form.type === 'stock' || form.type === 'etf') {
    const symbol = form.symbol || '';
    // 科创板（688开头）：最低200股
    if (symbol.startsWith('688')) return 200;
    // 北交所（8开头）：最低100股
    if (symbol.startsWith('8')) return 100;
    // 主板、创业板：100股
    return 100;
  }

  return 1;
}

// 卖出最小数量：不足一手时等于剩余全部，否则等于一手
function getSellMin(): number {
  const total = selectedPosition.value?.quantity ?? 0;
  const step = getStepForSecurity();
  // 不足一手时，只能全卖
  if (total < step) return total;
  // 否则最小为一手
  return step;
}

// 卖出快捷比例操作
const sellQuickRatios = [
  { label: '全部', value: 1 },
  { label: '1/4', value: 1 / 4 },
  { label: '1/3', value: 1 / 3 },
  { label: '1/2', value: 1 / 2 },
  { label: '3/4', value: 3 / 4 },
];

function applySellQuickRatio(ratio: number) {
  const total = selectedPosition.value?.quantity ?? 0;
  const step = getStepForSecurity();

  if (ratio === 1) {
    // 全部卖出
    form.quantity = total;
    return;
  }

  // 计算目标数量并向下取整到步长
  let target = Math.floor(total * ratio / step) * step;

  // 不足一手时，如果计算结果为0，则设为最小值
  if (target < step && total >= step) {
    target = step;
  }

  form.quantity = Math.max(target, step);
}

// 是否允许超过最低数量后以1股递增
function allowOneShareIncrement(): boolean {
  if (form.type === 'fund') return true;
  const market = form.market || 'CN_A';
  if (market === 'US' || market === 'CRYPTO') return true;
  if (market === 'CN_HK') return false; // 港股必须整数手
  if (form.type === 'bond') return false; // 可转债必须整数手

  // A股：科创板、北交所支持1股递增
  const symbol = form.symbol || '';
  if (symbol.startsWith('688') || symbol.startsWith('8')) return true;
  return false; // 主板、创业板必须整数手
}

// 根据品种返回小数精度
function getPrecisionForSecurity(): number {
  if (form.type === 'fund') return 4;       // 基金：4位小数
  if (form.type === 'stock' || form.type === 'etf' || form.type === 'bond') return 0; // 整数
  return 0;
}

function isWeekend(dateStr: string): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  return d.getDay() === 0 || d.getDay() === 6;
}

function applyFeePreset() {
  if (isSellLike.value) {
    form.fee = 0;
    return;
  }

  const config = getAccountFeeConfig(form.account_name);
  if (!config) {
    form.fee = 0;
    return;
  }

  const ledger = ledgers.value.find(l => l.name === form.account_name);
  if (!ledger) return;

  if (ledger.ledger_type === 'stock' && amountOrQuantity.value > 0) {
    // 根据当前输入的金额（或份额推算的金额）计算手续费，只计算一次
    const estimatedAmount = amountMode.value === 'amount'
      ? amountOrQuantity.value
      : amountOrQuantity.value * form.price;
    const rate = config.commission?.rate || 0.00025;
    form.fee = estimatedAmount * rate;
  } else if (ledger.ledger_type === 'fund') {
    const discount = config.subscription_discount ?? 0.1;
    fundFeeDiscount.value = discount;
    const fundRate = selectedSecurityOption.value?.subscription_rate || SEC_DEFAULTS.subscription_rate;
    const estimatedAmount = amountMode.value === 'amount'
      ? amountOrQuantity.value
      : amountOrQuantity.value * form.price;
    form.fee = estimatedAmount * fundRate * discount;
  }
}

function onFundFeeDiscountChange() {
  const fundRate = selectedSecurityOption.value?.subscription_rate || SEC_DEFAULTS.subscription_rate;
  form.fee = computedAmount.value * fundRate * fundFeeDiscount.value;
}

// 切换金额/份额模式
function toggleAmountMode() {
  const currentVal = amountOrQuantity.value;
  if (amountMode.value === 'amount') {
    amountMode.value = 'quantity';
    if (form.price > 0) {
      const rawQty = Math.max(0, currentVal - form.fee) / form.price;
      const step = getStepForSecurity();
      if (allowOneShareIncrement()) {
        // 科创板/北交所/美股：不低于最低数量即可，不强制整数手
        amountOrQuantity.value = Math.max(step, Math.floor(rawQty));
      } else {
        // 主板/港股/可转债：必须向下取整到整数手
        amountOrQuantity.value = Math.max(0, Math.floor(rawQty / step) * step);
      }
    } else {
      amountOrQuantity.value = 0;
    }
  } else {
    amountMode.value = 'amount';
    amountOrQuantity.value = currentVal * form.price + form.fee;
  }
}

// ── 操作类型切换 ──
function onOpTypeChange() {
  if (form.opType === 'sell') {
    fetchPositionsByAccount();
  }
}


async function quickCreateAccount() {
  const name = newAccountName.value.trim();
  if (!name) return;

  creatingAccount.value = true;
  try {
    // 自动推断账户类型
    const inferredType = selectedSecurityOption.value?.type === 'fund' ? 'fund' : 'stock';

    // 默认费率配置
    const defaultFeeConfig = inferredType === 'fund'
      ? { subscription_discount: 0.1 }  // 基金默认打1折
      : { commission: { rate: 0.00025, min: null } };  // 股票默认万2.5免5

    const res = await createLedgerApi({
      name,
      ledger_type: inferredType,
      fee_config: defaultFeeConfig,
    });

    const newLedger = (res as any)?.data ?? res;

    // 刷新账户列表
    await loadLedgers();

    // 自动选中新创建的账户
    form.account_name = newLedger.name || name;

    // 重新计算费率
    applyFeePreset();

    // 关闭创建表单
    showQuickAddAccount.value = false;
    newAccountName.value = '';

    ElMessage.success(`已创建账户「${newLedger.name || name}」并自动选中`);
  } catch (e: any) {
    ElMessage.error(e?.message || '创建账户失败');
  } finally {
    creatingAccount.value = false;
  }
}

// ── 获取可卖持仓 ──

async function fetchPositionsByAccount() {
  try {
    const res = await getPositions({ group_by: 'account' });
    // getPositions 返回的数据结构：{ data: { 账户名: [...] }, message: 'ok' }
    positionsByAccount.value = (res as any)?.data ?? {};
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
  form.quantity = pos.quantity;
  form.price = pos.current_price ?? pos.avg_price;
}

// ── 证券搜索（统一入口）──
const remoteSearch = async (query: string) => {
  if (!query) {
    securityOptions.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    // 尝试证券搜索（股票、可转债、ETF）
    const secRes = await searchSecurities(query);
    const secArr = Array.isArray(secRes) ? secRes : (secRes as any)?.data ?? [];
    const secOptions = secArr.map((s: any) => ({
      symbol: s.symbol,
      name: s.name,
      market: s.market,
      type: s.type, // stock/bond/etf
      type_label: typeLabels[s.type] || s.type,
    }));

    // 基金搜索
    const fundRes = await searchFunds(query);
    const fundArr = Array.isArray(fundRes) ? fundRes : (fundRes as any)?.data ?? [];
    const fundOptions = fundArr.map((f: any) => ({
      symbol: f.code,
      name: f.name,
      market: 'CN_A',
      type: 'fund',
      type_label: '基金',
      subscription_rate: f.subscription_rate || SEC_DEFAULTS.subscription_rate,
    }));

    securityOptions.value = [...secOptions, ...fundOptions];
    if (securityOptions.value.length === 0 && query.trim()) {
      securityOptions.value = [{
        symbol: query.trim().toUpperCase(),
        name: query.trim(),
        market: 'CN_A',
        type: 'stock',      // 默认类型，用户可以手动修改
        type_label: '手动输入',
        is_manual: true,     // 标记为手动输入
      }];
    }
  } catch (e) {
     if (query.trim()) {
      securityOptions.value = [{
        symbol: query.trim().toUpperCase(),
        name: query.trim(),
        market: 'CN_A',
        type: 'stock',
        type_label: '手动输入',
        is_manual: true,
      }];
    }
    ElMessage.warning('搜索服务暂不可用，已提供手动输入选项');
  } finally {
    searchLoading.value = false;
  }
};

const typeLabels: Record<string, string> = {
  stock: '股票',
  bond: '可转债',
  etf: 'ETF',
  fund: '基金',
};

// 选中证券后处理
const onSecuritySelected = (option: any) => {
  if (!option) {
    form.symbol = '';
    form.name = '';
    form.market = 'CN_A';
    form.type = 'stock';
    return;
  }
  form.symbol = option.symbol;
  form.name = option.name;
  form.market = option.market || 'CN_A';
  form.type = option.type;

  // ⭐ 后期：如果后端返回了净值或价格区间，存储备用
  if (option.latest_nav) {
    // 基金净值，后期自动填充
    selectedSecurityOption.value = { ...option, _latestNav: option.latest_nav };
  } else if (option.price_range) {
    // 股票当日成交价区间，后期用于输入校验
    selectedSecurityOption.value = { ...option, _priceRange: option.price_range };
  }
  selectedSecurityOption.value = option;
  applyFeePreset();
};

// ── 表单校验 ──
const rules = computed<FormRules>(() => {
  const baseRules: FormRules = {
    opType: [{ required: true, message: '请选择操作', trigger: 'change' }],
    symbol: [{ required: true, message: '请选择证券', trigger: 'change' }],
    account_name: [{ required: true, message: '请选择账户', trigger: 'change' }],
    purchase_date: [{ required: true, message: '请选择日期', trigger: 'change' }],
  };

  // 买入时增加价格和金额必填
  if (form.opType === 'buy') {
    baseRules.price = [{ required: true, message: '请输入成交价格', trigger: 'blur' }];
    baseRules.amountOrQuantity = [
      {
        validator: (_rule, _value, callback) => {
          if (amountOrQuantity.value <= 0) callback(new Error('请输入金额或份额'));
          else callback();
        },
        trigger: 'blur',
      },
    ];
  }

  // 卖出时增加数量和价格必填
  if (form.opType === 'sell') {
    baseRules.quantity = [{ required: true, message: '请输入卖出数量', trigger: 'blur' }];
    baseRules.price = [{ required: true, message: '请输入卖出价格', trigger: 'blur' }];
  }

  return baseRules;
});

// ── 提交逻辑 ──
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  submitting.value = true;
  try {
    let quantity = 0;
    let price = 0;
    let amount = 0;

    if (form.opType === 'buy') {
      // 买入：使用金额/份额切换逻辑
      quantity = amountMode.value === 'amount' ? computedQuantity.value : amountOrQuantity.value;
      price = form.price;
      amount = computedAmount.value;

      // 买入校验：最低数量和整数倍
      const step = getStepForSecurity();
      if (quantity < step) {
        ElMessage.error(`${form.type === 'fund' ? '申购份额' : '买入数量'}不能低于 ${step} ${form.type === 'fund' ? '份' : '股'}`);
        return;
      }
      if (!allowOneShareIncrement() && quantity % step !== 0) {
        ElMessage.error(`${form.type === 'bond' ? '可转债' : '股票'}买入数量必须是 ${step} 的整数倍`);
        return;
      }
    } else {
      // 卖出：直接使用表单中的数量和价格
      quantity = form.quantity;
      price = form.price;
      amount = quantity * price;

      // 卖出校验：数量不能为0
      if (quantity <= 0) {
        ElMessage.error('请输入卖出数量');
        return;
      }
      if (price <= 0) {
        ElMessage.error('请输入卖出价格');
        return;
      }
    }

    const purchaseDate = form.purchase_date || new Date().toISOString().slice(0, 10);

    const body: any = {
      symbol: form.symbol,
      name: form.name,
      op_type: form.opType,
      position_id: form.positionId || undefined,
      market: form.market,
      type: form.type,
      account_name: form.account_name,
      quantity: quantity,
      avg_price: price,
      amount: amount,
      currency: form.currency || 'CNY',
      purchase_date: purchaseDate,
      confirm_date: form.opType === 'buy' && form.type === 'fund' ? confirmDate.value : null,
      fee: form.fee,
      notes: form.notes,
      allocation: form.allocation,
      isAfter15: form.isAfter15,
    };

    await createPosition(body);
    ElMessage.success('记账成功');
    visible.value = false;
    emit('submitted');
  } catch (e: any) {
    ElMessage.error(e?.message || '记账失败');
  } finally {
    submitting.value = false;
  }
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedPosition.value = null;
  positionsByAccount.value = {};
  securityOptions.value = [];
  selectedSecurityOption.value = null;
  amountOrQuantity.value = 0;
  amountMode.value = 'amount';
  fundFeeDiscount.value = 0.1;
  formRef.value?.resetFields();
}

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  submitted: [];
}>();

const props = defineProps<{ modelValue: boolean }>();
const visible = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});

// 引导链接
function goToInventory() {
  emit("update:modelValue", false);
  // 跳转逻辑由父组件处理，或者通过 router
}

watch([() => form.purchase_date, () => form.isAfter15, () => selectedSecurityOption.value], () => {
  fetchTradingDay();
  fetchConfirmDate();
});
// 初始化时加载账户列表
onMounted(() => {
  loadLedgers();
});

</script>

<style scoped>

.allocation-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  width: 100%;
}

.fee-form-item :deep(.el-form-item__label) {
  text-align: right;
}

.allocation-group .el-radio-button {
  width: 100%;
}

.allocation-group .el-radio-button__inner {
  width: 100%;
  text-align: center;
}

.el-input.is-disabled .el-input__wrapper {
  background-color: var(--bg-muted);
  box-shadow: none;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
}

:deep(.el-input-number.is-without-controls .el-input__inner) {
  text-align: right;
}

.text-xs.text-gray-500 {
  color: var(--text-secondary);
}

:deep(.el-drawer__footer) {
  position: sticky;
  bottom: 0;
  background: var(--bg-card);
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
  z-index: 10;
}

/* 调整抽屉宽度 */
:deep(.el-drawer__body) {
  padding: 20px;
}
</style>
