import type { Ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { usePositionSubmit } from "@/composables/usePositionSubmit";
import {
  checkPriceInRange,
  createStockPriceValidator,
  type useSecurityPriceRange
} from "@/composables/useSecurityPrice";
import { buildBuyPayload } from "../buyFormPayload";
import {
  buildBuySnapshot,
  isSameAsLastSubmitted,
  loadBuyLastSubmitted,
  saveBuyLastSubmitted,
  type BuyLastSubmitted
} from "../buyLastSubmitted";
import { bumpRecentLedger } from "../buyRecentLedgers";
import type { SecurityOption } from "./useSecuritySearch";
import type { FeeMode } from "./useBuyFee";

type StockPriceRange = ReturnType<typeof useSecurityPriceRange>["priceRange"];

/**
 * 防呆：与上次提交完全一致时弹确认，避免同一笔记两遍（#2305）。
 * 比对口径见 isSameAsLastSubmitted（只比 6 个「同一笔」判据）。
 */
async function confirmSameAsLastSubmitted(
  current: BuyLastSubmitted
): Promise<boolean> {
  const last = loadBuyLastSubmitted();
  if (!last || !isSameAsLastSubmitted(last, current)) return true;
  return new Promise<boolean>(resolve => {
    ElMessageBox.confirm(
      "当前记录与上次提交完全相同，确认要重复记录吗？",
      "重复记录确认",
      {
        confirmButtonText: "继续记录",
        cancelButtonText: "取消",
        type: "warning",
        distinguishCancelAndClose: true
      }
    )
      .then(() => resolve(true))
      .catch(() => resolve(false));
  });
}

interface BuySubmitForm {
  ledger_id: number | null;
  symbol: string;
  name: string;
  market: string;
  type: string;
  price: number | undefined;
  buyAmount: number | undefined;
  shares: number | undefined;
  fee: number | undefined;
  currency: string;
  trade_date: string;
  notes: string;
  allocation: string;
  isAfter15: boolean;
}

/**
 * 买入表单的校验规则 + 提交编排（#980 从 BuyForm 拆出）。
 *
 * 校验口径两个易错点都在这里：
 * 1. 份额：净值缺失（navMissing）时允许留空 —— 后端按金额与最近净值占位建仓、标
 *    pending_nav，官方净值到位后回填；其余情况必填。
 * 2. 价格：股票走 useSecurityPrice 的区间校验（#948），基金不校验。
 *
 * 提交链路本身不碰 UI 广播：成功回调交给调用方（父组件 emit submit-success）。
 */
export function useBuySubmit(deps: {
  form: BuySubmitForm;
  formRef: Ref<FormInstance | undefined>;
  selectedSecurityOption: Ref<SecurityOption | null>;
  stockPriceRange: StockPriceRange;
  navMissing: Ref<boolean>;
  /** 账户名（提交时读取，账户可能在填单过程中被切换） */
  getAccountName: () => string;
  confirmDate: Ref<string>;
  actualNavDate: Ref<string>;
  feeMode: Ref<FeeMode>;
  onSuccess: () => void;
}) {
  const { form } = deps;

  const rules: FormRules = {
    ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
    symbol: [{ required: true, message: "请选择买入产品", trigger: "change" }],
    trade_date: [{ required: true, message: "请选择日期", trigger: "change" }],
    buyAmount: [{ required: true, message: "请输入买入金额", trigger: "blur" }],
    shares: [
      {
        validator: (
          _rule: unknown,
          value: unknown,
          callback: (err?: Error) => void
        ) => {
          // 净值缺失先记账：份额允许留空（后端按金额/占位价暂算，官方净值到位后回填）
          if (
            deps.navMissing.value &&
            (value === undefined || value === null)
          ) {
            callback();
            return;
          }
          if (value === undefined || value === null || value === "") {
            callback(new Error("确认份额不能为空"));
            return;
          }
          callback();
        },
        trigger: ["blur", "change"]
      }
    ],
    allocation: [
      { required: true, message: "请选择配置目标", trigger: "change" }
    ],
    price: [
      {
        validator: createStockPriceValidator(
          () => deps.stockPriceRange.value,
          () => deps.selectedSecurityOption.value?.type === "stock"
        ),
        trigger: ["blur", "change"]
      }
    ]
  };

  async function handleSubmit(): Promise<void> {
    const valid = await deps.formRef.value?.validate().catch(() => false);
    if (!valid) return;
    // 净值缺失先记账：份额允许留空/为 0，后端按最近净值占位建仓、标 pending_nav，
    // 官方净值落库后由 nav_backfill 回填份额与成本
    const navPending = form.type === "fund" && deps.navMissing.value;
    const quantity = form.shares ?? 0;
    if (!navPending && quantity <= 0) {
      ElMessage.error("确认份额必须大于0");
      return;
    }

    // 股票价格区间校验（#948）：统一走 useSecurityPrice.checkPriceInRange
    const priceErr = checkPriceInRange(
      form.price ?? 0,
      deps.stockPriceRange.value,
      deps.selectedSecurityOption.value?.type === "stock"
    );
    if (priceErr) {
      ElMessage.error(priceErr);
      return;
    }

    const snapshot = buildBuySnapshot(form);
    const body = buildBuyPayload({
      form,
      accountName: deps.getAccountName(),
      quantity,
      confirmDate: deps.confirmDate.value ?? "",
      navPending,
      navDate: deps.actualNavDate.value ?? "",
      feeMode: deps.feeMode.value
    });

    // 统一提交层（#933）：防抖/错误信封/成功广播单点维护，表单只组装 body
    const { submitPosition } = usePositionSubmit();

    // 防呆：若与上次提交完全一致，先确认是否重复记录（#2305）
    if (!(await confirmSameAsLastSubmitted(snapshot))) return;

    const ok = await submitPosition(body);
    if (ok) {
      saveBuyLastSubmitted(snapshot);
      if (form.ledger_id) bumpRecentLedger(form.ledger_id);
      deps.onSuccess();
    }
  }

  return { rules, handleSubmit };
}
