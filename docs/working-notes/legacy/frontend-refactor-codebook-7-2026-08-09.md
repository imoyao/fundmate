# batch7 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch7/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?6 涓枃浠躲€?

## `composables/trade/index.ts`

```ts
// src/composables/trade/index.ts
export * from "./types";
export * from "./useTradeForm";
```

## `composables/trade/types.ts`

```ts
// src/composables/trade/types.ts
//
// BuyForm / SellForm 鍚堝苟鍚庣殑鍏变韩绫诲瀷銆?// 琛ㄥ崟妯″瀷涓轰袱鑰呭瓧娈电殑銆屽苟闆嗐€嶏紝鐢?mode 鎺у埗蹇呭～/鍙銆?
export type TradeMode = "buy" | "sell";

/** 鍚堝苟鍚庣殑浜ゆ槗琛ㄥ崟妯″瀷锛坆uy + sell 瀛楁骞堕泦锛?*/
export interface TradeFormModel {
  ledger_id: number | null;
  positionId: number | null; // 浠呭崠鍑虹敤
  symbol: string;
  name: string;
  market: string;
  type: string;
  price: number | undefined;
  trade_date: string;
  confirm_date: string;
  fee: number | undefined;
  allocation: string; // 浠呬拱鍏ョ敤
  notes: string;
  isAfter15: boolean;
  currency: string;
  buyAmount: number | undefined; // 浠呬拱鍏ョ敤
  shares: number | undefined; // 浠呬拱鍏ョ敤
  quantity: number | undefined; // 浠呭崠鍑虹敤
}

/** BuyForm / SellForm / TradeForm 鍏叡 props */
export interface TradeFormProps {
  ledgers: any[];
  hideAccountSelect?: boolean;
  defaultLedgerId?: number | null;
}
```

## `composables/trade/useTradeForm.ts`

```ts
// src/composables/trade/useTradeForm.ts
//
// 鍚堝苟 BuyForm / SellForm 鐨勩€屽叡浜€昏緫銆嶏紙涓よ€呴噸澶嶇害 60%锛夛細
//   - 璐︽埛閫夋嫨 + 蹇嵎寤鸿处锛堜袱涓〃鍗曞畬鍏ㄤ竴鏍凤級
//   - 褰撳墠璐︽埛 / 鍙氦鏄撹处鎴?璁＄畻灞炴€э紙涓€鏍凤級
//   - 鍩洪噾鍑€鍊兼棩鏈?confirmDate / actualNavDate + 浜ゆ槗鏃?checkTradingDay锛堜竴鏍凤級
//   - disabledDate锛堜竴鏍凤級
//   - formRef / handleSubmit锛堟牎楠?+ createPosition锛? resetForm锛堜竴鏍凤級
//   - defineExpose(handleSubmit, resetForm)锛堜竴鏍凤級
// 宸紓閮ㄥ垎锛堜拱鍏ョ殑璇佸埜鎼滅储/閲戦浠介/閰嶇疆锛屽崠鍑虹殑鎸佷粨鏌ヨ/鏁伴噺/璧庡洖璐圭巼锛夌暀鍦?// TradeForm.vue 鐨?mode 鏉′欢鍧楅噷锛岃皟鐢ㄦ湰 composable 鍏变韩鐨勭姸鎬併€?//
// 鑱岃矗锛氭湰鏂囦欢鍙斁鍏变韩閫昏緫锛涙ā寮忕浉鍏?API/澶勭悊鍣ㄥ湪 TradeForm.vue 灞€閮ㄥ紩鍏ャ€?
import { ref, reactive, computed } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import { createPosition } from "@/api/positions";
import { createLedger as createLedgerApi } from "@/api/ledger";
import { checkTradingDay, calcFundConfirmDate } from "@/api/utils";
import { LEDGER_TYPE_OPTIONS } from "@/constants";
import type { TradeFormProps, TradeFormModel, TradeMode } from "./types";

export function defaultForm(): TradeFormModel {
  return {
    ledger_id: null,
    positionId: null,
    symbol: "",
    name: "",
    market: "CN_A",
    type: "stock",
    price: undefined,
    trade_date: new Date().toISOString().slice(0, 10),
    confirm_date: "",
    fee: 0,
    allocation: "longterm",
    notes: "",
    isAfter15: false,
    currency: "CNY",
    buyAmount: undefined,
    shares: undefined,
    quantity: undefined,
  };
}

export function useTradeForm(
  props: TradeFormProps,
  emit: (e: string, ...args: any[]) => void,
  mode: TradeMode,
) {
  const formRef = ref<FormInstance>();
  const form = reactive<TradeFormModel>(defaultForm());

  // 鈹€鈹€ 璐︽埛閫夋嫨 + 蹇嵎寤鸿处锛堜袱琛ㄥ崟閲嶅锛屽凡鍚堝苟锛夆攢鈹€
  const showQuickAdd = ref(false);
  const newAccountName = ref("");
  const newAccountType = ref("");
  const creatingAccount = ref(false);
  const quickAddTypeOptions = computed(() =>
    LEDGER_TYPE_OPTIONS.filter((opt: any) => opt.value !== "property"),
  );
  const quickCreateAccount = async () => {
    // TODO: 鎼師 BuyForm/SellForm 鐨?quickCreateAccount锛坈reateLedgerApi + loadLedgers锛?    // 娉ㄦ剰锛氬缓璐﹀悗闇€閫氱煡鐖剁骇鍒锋柊璐︽埛鍒楄〃 鈫?emit("accounts-changed")
  };
  const resetQuickAdd = () => {
    newAccountName.value = "";
    newAccountType.value = "";
    showQuickAdd.value = false;
  };

  // 鈹€鈹€ 褰撳墠璐︽埛 / 鍙氦鏄撹处鎴凤紙涓よ〃鍗曢噸澶嶏級鈹€鈹€
  const currentLedger = computed(() =>
    props.ledgers.find((l: any) => l.id === form.ledger_id),
  );
  const selectableLedgers = computed(() =>
    props.ledgers.filter((l: any) => l.ledger_type !== "property"),
  );
  const accountName = computed(() => currentLedger.value?.name ?? "");

  // 鈹€鈹€ 鍩洪噾鍑€鍊兼棩鏈?/ 浜ゆ槗鏃ワ紙涓よ〃鍗曢噸澶嶏級鈹€鈹€
  const confirmDate = ref("");
  const actualNavDate = ref("");
  const isTradingDay = ref<boolean | null>(null);
  const fetchTradingDay = async () => {
    // TODO: checkTradingDay(form.trade_date) 鈫?isTradingDay
  };
  const fetchConfirmDate = async () => {
    // TODO: calcFundConfirmDate(form.trade_date, form.isAfter15) 鈫?confirmDate/actualNavDate
  };

  const disabledDate = (time: Date): boolean => {
    // TODO: 鎼師 disabledDate锛堝绂佹鏈潵鏃ユ湡锛?    return time.getTime() > Date.now();
  };

  // 鈹€鈹€ 鏍￠獙瑙勫垯锛氬叕鍏?+ 妯″紡宸紓 鈹€鈹€
  const validateQuantity = (_rule: any, value: any, callback: any) => {
    // TODO: 鎼師 SellForm.validateQuantity锛堟寜 type 鍖哄垎鎶ラ敊鏂囨锛?    if (value == null || value === "") callback(new Error("璇疯緭鍏ュ崠鍑烘暟閲?));
    else callback();
  };

  const rules = computed<FormRules>(() => {
    const base: FormRules = {
      ledger_id: [{ required: true, message: "璇烽€夋嫨璐︽埛", trigger: "change" }],
      trade_date: [{ required: true, message: "璇烽€夋嫨鏃ユ湡", trigger: "change" }],
    };
    if (mode === "buy") {
      return {
        ...base,
        symbol: [{ required: true, message: "璇烽€夋嫨涔板叆浜у搧", trigger: "change" }],
        buyAmount: [{ required: true, message: "璇疯緭鍏ヤ拱鍏ラ噾棰?, trigger: "blur" }],
        shares: [{ required: true, message: "纭浠介涓嶈兘涓虹┖", trigger: "blur" }],
        allocation: [
          { required: true, message: "璇烽€夋嫨閰嶇疆鐩爣", trigger: "change" },
        ],
      };
    }
    return {
      ...base,
      positionId: [
        { required: true, message: "璇烽€夋嫨鎸佷粨浜у搧", trigger: "change" },
      ],
      quantity: [{ validator: validateQuantity, trigger: "blur" }],
    };
  });

  // 鈹€鈹€ 鏋勫缓鎻愪氦 payload锛堟ā寮忓樊寮傦級鈹€鈹€
  const buildPayload = () => {
    const common = {
      ledger_id: form.ledger_id,
      symbol: form.symbol,
      name: form.name,
      market: form.market,
      type: form.type,
      price: form.price,
      trade_date: form.trade_date,
      fee: form.fee,
      currency: form.currency,
      isAfter15: form.isAfter15,
      notes: form.notes,
    };
    if (mode === "buy") {
      return { ...common, allocation: form.allocation, shares: form.shares };
    }
    return { ...common, position_id: form.positionId, quantity: form.quantity };
  };

  const handleSubmit = async () => {
    if (!formRef.value) return;
    await formRef.value.validate();
    await createPosition(buildPayload());
    emit("submit-success");
  };

  const resetForm = () => {
    formRef.value?.resetFields();
    Object.assign(form, defaultForm());
  };

  return {
    mode,
    formRef,
    form,
    rules,
    // 璐︽埛 + 蹇嵎寤鸿处
    showQuickAdd,
    newAccountName,
    newAccountType,
    creatingAccount,
    quickAddTypeOptions,
    quickCreateAccount,
    resetQuickAdd,
    // 璐︽埛璁＄畻灞炴€?    currentLedger,
    selectableLedgers,
    accountName,
    // 鍩洪噾鍑€鍊兼棩鏈?    confirmDate,
    actualNavDate,
    isTradingDay,
    fetchTradingDay,
    fetchConfirmDate,
    disabledDate,
    // 鎻愪氦 / 閲嶇疆
    handleSubmit,
    resetForm,
  };
}
```

## `components/QuickEntry/BuyForm.vue`

```vue
<script setup lang="ts">
import { ref } from "vue";
import TradeForm from "./TradeForm.vue";
import type { TradeFormProps } from "@/composables/trade";

// 钖勫３锛氫繚鎸佸師 BuyForm 鐨勫叕鍏?API锛坢anual/index.vue 鐢?ref 璋?handleSubmit/resetForm锛?// 涓旂洃鍚?submit-success / accounts-changed锛夛紝鍐呴儴濮旀墭缁欏叡浜?TradeForm(mode="buy")銆?const props = defineProps<TradeFormProps>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "accounts-changed"): void;
}>();

const tradeFormRef = ref<InstanceType<typeof TradeForm>>();

defineExpose({
  handleSubmit: () => tradeFormRef.value?.handleSubmit(),
  resetForm: () => tradeFormRef.value?.resetForm(),
});
</script>

<template>
  <TradeForm
    ref="tradeFormRef"
    mode="buy"
    :ledgers="ledgers"
    :hide-account-select="hideAccountSelect"
    :default-ledger-id="defaultLedgerId"
    @submit-success="emit('submit-success')"
    @accounts-changed="emit('accounts-changed')"
  />
</template>
```

## `components/QuickEntry/SellForm.vue`

```vue
<script setup lang="ts">
import { ref } from "vue";
import TradeForm from "./TradeForm.vue";
import type { TradeFormProps } from "@/composables/trade";

// 钖勫３锛氫繚鎸佸師 SellForm 鐨勫叕鍏?API锛坢anual/index.vue 鐢?ref 璋?handleSubmit/resetForm锛?// 涓旂洃鍚?submit-success / close / go-to-inventory / positions-loaded / go-sync锛夛紝
// 鍐呴儴濮旀墭缁欏叡浜?TradeForm(mode="sell")銆?const props = defineProps<TradeFormProps>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "close"): void;
  (e: "go-to-inventory"): void;
  (e: "positions-loaded", ledgerIds: number[]): void;
  (e: "go-sync"): void;
}>();

const tradeFormRef = ref<InstanceType<typeof TradeForm>>();

defineExpose({
  handleSubmit: () => tradeFormRef.value?.handleSubmit(),
  resetForm: () => tradeFormRef.value?.resetForm(),
});
</script>

<template>
  <TradeForm
    ref="tradeFormRef"
    mode="sell"
    :ledgers="ledgers"
    :hide-account-select="hideAccountSelect"
    :default-ledger-id="defaultLedgerId"
    @submit-success="emit('submit-success')"
    @close="emit('close')"
    @go-to-inventory="emit('go-to-inventory')"
    @positions-loaded="(ids) => emit('positions-loaded', ids)"
    @go-sync="emit('go-sync')"
  />
</template>
```

## `components/QuickEntry/TradeForm.vue`

```vue
<script setup lang="ts">
import { ref, watch, computed } from "vue";
import { useTradeForm } from "@/composables/trade";
import type { TradeFormProps, TradeMode } from "@/composables/trade";
import { IconifyIconOffline } from "@/components/ReIcon";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { ALLOCATION_OPTIONS, LEDGER_TYPE_SHORT } from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";

const props = defineProps<{ mode: TradeMode } & TradeFormProps>();

const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "accounts-changed"): void;
  (e: "close"): void;
  (e: "go-to-inventory"): void;
  (e: "positions-loaded", ledgerIds: number[]): void;
  (e: "go-sync"): void;
}>();

const {
  formRef,
  form,
  rules,
  showQuickAdd,
  newAccountName,
  newAccountType,
  creatingAccount,
  quickAddTypeOptions,
  quickCreateAccount,
  resetQuickAdd,
  selectableLedgers,
  accountName,
  confirmDate,
  actualNavDate,
  isTradingDay,
  fetchTradingDay,
  fetchConfirmDate,
  disabledDate,
  handleSubmit,
  resetForm,
} = useTradeForm(props, emit as (e: string, ...args: any[]) => void, props.mode);

// default-ledger-id 鍒濆鍖栵紙鍘熶袱琛ㄥ崟鍧囨湁姝ら€昏緫锛?watch(
  () => props.defaultLedgerId,
  (v) => {
    if (v != null) form.ledger_id = v;
  },
  { immediate: true },
);

const showIsAfter15 = computed(() => {
  // TODO: 鎼師 showIsAfter15锛堝鍩洪噾/鑲＄エ涓旈潪褰撴棩绛夋潯浠讹級
  return true;
});

// 鈹€鈹€ 妯″紡鐩稿叧澶勭悊鍣紙鍚勮嚜鐨?API锛岀暀鍦ㄧ粍浠跺眰锛岄伩鍏?composable 鑶ㄨ儉锛夆攢鈹€
// TODO(buy):  remoteSearch / onSecuritySelected / applyFeePreset / onFeeModeChange /
//             onFundFeeDiscountChange  鈥斺€?searchSecurities, searchFunds, calcFundNav,
//             getFundFeeRates, DEFAULT_SUB_RATE
// TODO(sell): fetchPositionsByAccount / onAccountChange / onPositionSelect /
//             fetchFundFeeRules / calculateFeeAndRate / openFeeRateDialog /
//             applySellQuickRatio  鈥斺€?getPositions, validateTradeOrder,
//             estimateRedeemFee, syncFundFees, SELL_QUICK_RATIOS, getStep

defineExpose({ handleSubmit, resetForm });
</script>

<template>
  <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
    <!-- ===== 妯″潡涓€锛氳处鎴烽€夋嫨鍖猴紙鍏变韩锛?===== -->
    <div v-if="!hideAccountSelect" class="trade-account-select">
      <el-select
        v-model="form.ledger_id"
        class="account-select"
        placeholder="璇烽€夋嫨浜ゆ槗璐︽埛"
        filterable
        size="large"
      >
        <el-option
          v-for="ledger in selectableLedgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        >
          <div class="flex items-center justify-between w-full">
            <span>{{ ledger.name }}</span>
            <AssetTypeBadge :type="ledger.ledger_type" variant="tag" />
          </div>
        </el-option>
      </el-select>
      <el-button
        v-if="!showQuickAdd"
        type="primary"
        text
        size="small"
        @click="showQuickAdd = true"
      >
        <IconifyIconOffline icon="ep:plus" class="mr-1" /> 鏂板缓璐︽埛
      </el-button>
    </div>

    <!-- 蹇嵎寤鸿处锛堝叡浜級 -->
    <div v-if="showQuickAdd" class="quick-add-panel">
      <el-input v-model="newAccountName" placeholder="杈撳叆璐︽埛鍚嶇О" size="small" />
      <el-select v-model="newAccountType" class="w-full mt-2" size="small" placeholder="閫夋嫨璐︽埛绫诲瀷">
        <el-option v-for="opt in quickAddTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <div class="flex justify-end gap-2 mt-2">
        <el-button size="small" @click="resetQuickAdd">鍙栨秷</el-button>
        <el-button size="small" type="primary" :loading="creatingAccount" @click="quickCreateAccount">
          鍒涘缓骞堕€夋嫨
        </el-button>
      </div>
    </div>

    <!-- ===== 妯″潡浜岋細鏃ユ湡 + 15:00锛堝叡浜級 ===== -->
    <el-form-item label="浜ゆ槗鏃ユ湡" prop="trade_date">
      <el-date-picker
        v-model="form.trade_date"
        type="date"
        placeholder="閫夋嫨鏃ユ湡"
        :disabled-date="disabledDate"
        @change="fetchTradingDay"
      />
      <el-radio-group v-if="showIsAfter15" v-model="form.isAfter15" class="ml-3">
        <el-radio :value="false">15:00 鍓?/el-radio>
        <el-radio :value="true">15:00 鍚?/el-radio>
      </el-radio-group>
      <span v-if="isTradingDay === false" class="ml-2 text-xs text-orange-500">
        闈炰氦鏄撴棩
      </span>
    </el-form-item>

    <!-- ===== 涔板叆涓撳睘锛氳瘉鍒告悳绱?/ 閲戦 / 浠介 / 閰嶇疆 ===== -->
    <template v-if="mode === 'buy'">
      <el-form-item label="涔板叆浜у搧" prop="symbol">
        <!-- TODO: 杩滅▼鎼滅储 el-select锛岀粦瀹?form.symbol / form.name -->
        <el-select v-model="form.symbol" filterable placeholder="鎼滅储鑲＄エ/鍩洪噾" />
      </el-form-item>
      <el-form-item label="涔板叆閲戦" prop="buyAmount">
        <el-input-number v-model="form.buyAmount" :min="0" />
      </el-form-item>
      <el-form-item label="纭浠介" prop="shares">
        <el-input-number v-model="form.shares" :min="0" />
      </el-form-item>
      <el-form-item label="閰嶇疆鐩爣" prop="allocation">
        <el-select v-model="form.allocation">
          <el-option
            v-for="opt in ALLOCATION_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
    </template>

    <!-- ===== 鍗栧嚭涓撳睘锛氭寔浠撻€夋嫨 / 鏁伴噺 / 浠锋牸 / 璐圭巼 ===== -->
    <template v-else>
      <el-form-item label="鎸佷粨浜у搧" prop="positionId">
        <!-- TODO: 鎸佷粨 el-select锛岀粦瀹?form.positionId锛坒etchPositionsByAccount锛?-->
        <el-select v-model="form.positionId" filterable placeholder="閫夋嫨鎸佷粨" />
      </el-form-item>
      <el-form-item label="鍗栧嚭鏁伴噺" prop="quantity">
        <el-input-number v-model="form.quantity" :min="0" />
        <!-- TODO: 蹇嵎姣斾緥鎸夐挳 applySellQuickRatio(SELL_QUICK_RATIOS) -->
      </el-form-item>
      <el-form-item v-if="form.type !== 'fund'" label="鍗栧嚭浠锋牸" prop="price">
        <el-input-number v-model="form.price" :min="0" />
      </el-form-item>
      <el-form-item label="鎵嬬画璐? prop="fee">
        <el-input-number v-model="form.fee" :min="0" />
        <!-- TODO: 鍩洪噾鏃垛€滄煡璇㈣垂鐜団€濇寜閽?鈫?fetchFundFeeRules -->
      </el-form-item>
    </template>

    <!-- ===== 鍏叡锛氬娉?===== -->
    <el-form-item label="澶囨敞" prop="notes">
      <el-input v-model="form.notes" type="textarea" />
    </el-form-item>
  </el-form>
</template>
```
