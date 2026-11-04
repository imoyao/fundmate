/**
 * 编辑交易弹窗的表单状态与联动（#980 从 TransactionEditDialog.vue 抽出）。
 *
 * ## 为什么是 composable 而不是子组件
 *
 * 这些联动全靠 `watch` 互相咬合，且**注册顺序就是语义**：
 *
 * 1. `[amount, price, fee]` → 反算份额（基金）
 * 2. `quantity` → 标记「用户手改过份额」
 * 3. `[quantity, price, fee]` → 正算金额（股票）
 * 4. `[trade_date, isAfter15]` → 算确认日 + 拉净值
 *
 * 第 1 条写回 `quantity` 会在同一次 flush 里触发第 2 条；靠 `recomputeWriting`
 * 这个「程序写入窗口」把它和用户手改区分开（窗口在 `nextTick` 里关）。顺序一变
 * （比如第 2 条排到第 1 条前面）就永远判不出手改，份额会被反算反复盖掉。
 *
 * 拆成子组件的话，`form` 要跨组件传、`formRef.validate()` 要 `defineExpose` 出去，
 * 顺序还看不见了——所以这里只搬状态，模板留在 SFC 里。
 */
import { computed, nextTick, ref, watch } from "vue";
import { updateLedgerTransaction } from "@/api/ledger";
import { useFundTradeDate } from "@/composables/useFundTradeDate";
import {
  createStockPriceValidator,
  useSecurityPriceRange
} from "@/composables/useSecurityPrice";
import {
  useFormDirty,
  useUnsavedChangesGuard
} from "@/composables/useUnsavedChangesGuard";
import { ElMessage } from "element-plus";
import { disabledTradeDate } from "@/utils/date";
import {
  blankForm,
  buildUpdatePayload,
  formSnapshotOf,
  isFundAssetType,
  isStockAssetType,
  quantityMeta,
  recalcAmount,
  recalcShares,
  resolveAssetType,
  type TransactionEditForm
} from "./transactionEditModel";

export function useTransactionEditForm(opts: {
  /** 当前交易记录（用 getter 保持响应性） */
  transaction: () => any;
  /** 产品代码，用于拉净值 */
  symbol: () => string | undefined;
  /** 外部传入的资产类型（优先级高于记录里的字段） */
  assetTypeOverride: () => string | undefined;
  /** 保存成功回调 */
  onSaved: (data: any) => void;
  /** 请求父层把弹窗关掉（`update:modelValue → false`） */
  onClose: () => void;
}) {
  const saving = ref(false);
  const formRef = ref();
  const form = ref<TransactionEditForm>(blankForm());

  // 初始化标记：防止 initForm 赋值时触发 watch 覆盖原始金额
  const isInitializing = ref(false);

  // ── 手动份额优先（净值回填的对手语义）──
  // 用户在弹窗里手改过份额后，amount/price/fee 的反算不得再覆盖份额；
  // 后端同款语义：pending 流水被手改份额即清 entry_status（ledger_write_service）。
  const sharesTouched = ref(false);
  // 反算写份额的短暂窗口：窗口内的 quantity 变化是程序写入，不算用户手改
  const recomputeWriting = ref(false);

  // 交易日期不允许选未来（#1835）：规则收在 utils/date，这里只留别名保持模板可读
  const disabledDate = disabledTradeDate;

  // 15:00 后下单（影响确认日计算）
  const isAfter15 = ref(false);

  // 基金交易日期联动 composable（calcFundConfirmDate + fetchFundNav）
  const {
    navLoading,
    confirmDate: confirmDateDisplay,
    calcConfirmAndNav
  } = useFundTradeDate();

  // 资产类型：多字段兜底检测（外部传入 → asset_type → type → security_type → position_type）
  const assetType = computed(() =>
    resolveAssetType(opts.transaction(), opts.assetTypeOverride())
  );

  // 证券（股票 / 可转债等）卖出价区间校验与日期联动，统一走 useSecurityPriceRange（#948）
  // 注意：必须在 assetType 之后声明，否则 const 暂时性死区会抛 ReferenceError
  const isStock = computed(() => isStockAssetType(assetType.value));
  const { priceRange: stockPriceRange } = useSecurityPriceRange(
    computed(() =>
      isStock.value ? opts.symbol() || opts.transaction()?.symbol : undefined
    ),
    computed(() => form.value.trade_date),
    isStock
  );

  // 基金类（含货币基金）按份额（小数）处理；其余按股 / 张（整数）
  const isFund = computed(() => isFundAssetType(assetType.value));

  // 是否手工编辑记录（未导入，import_hash 为空）：弹窗内展示对账提示，无需保存后弹窗
  const isManual = computed(() => opts.transaction()?.import_hash == null);

  const quantityPrecision = computed(
    () => quantityMeta(assetType.value).precision
  );
  const quantityStep = computed(() => quantityMeta(assetType.value).step);

  // 交易日期必填（确认日期由系统自动计算，不需用户输入）
  const rules = {
    trade_date: [
      {
        required: true,
        message: "请选择交易日期",
        trigger: ["blur", "change"]
      }
    ],
    price: [
      {
        validator: createStockPriceValidator(
          () => stockPriceRange.value,
          () => isStock.value
        ),
        trigger: ["blur", "change"]
      }
    ]
  };

  // ── 未保存离开保护（#1835）──
  // 脏状态交给共用的 useFormDirty：原先这里的 `initialSnapshot = ref("")` 与表单初值 `{}`
  // 比永不相等，**弹窗没打开就算“有未保存修改”**；叠上 onBeforeRouteLeave 后，
  // 用户在账户列表点卡片进详情都会被问「确定放弃吗？」（#1845 回归）。
  const { isDirty, markClean } = useFormDirty(() => form.value);

  const { onBeforeClose, requestClose: confirmThenClose } =
    useUnsavedChangesGuard(() => isDirty.value);

  function initForm() {
    isInitializing.value = true;
    const t = opts.transaction() || {};
    isAfter15.value = false;
    sharesTouched.value = false;
    form.value = formSnapshotOf(t);
    // 展示已有确认日期（若交易记录里有）
    confirmDateDisplay.value = t.confirm_date || "";
    // 未保存离开保护（#1835）的基线：弹窗打开时的表单快照
    markClean();
    nextTick(() => {
      isInitializing.value = false;
    });
  }

  /**
   * 关闭后把表单与基线一起清空（#1880，与 AssetEditDialog / CreateAccountDialog 同源）。
   *
   * `@open="initForm"` 只覆盖打开这一侧。关闭侧以前完全没处理，于是「保存」与「放弃修改」
   * 都只是 `modelValue → false`，表单里留着改后的值而基线还是打开时的值 → `isDirty` 为 true，
   * 叠上 `onBeforeRouteLeave` 就是「关掉弹窗后点侧边栏仍弹未保存修改、导航被拦死」。
   *
   * 挂 `@close` 而非 `before-close`：后者是**询问**是否关闭，用户点「继续编辑」时不能复位。
   */
  function resetAfterClose() {
    form.value = blankForm();
    confirmDateDisplay.value = "";
    markClean();
  }

  async function requestClose() {
    await confirmThenClose(() => opts.onClose());
  }

  // ── 联动（顺序即语义，见文件头注释）──

  // 基金：amount / nav / fee 变化 → 反算 shares（用户手改过份额则让位，手动优先）
  watch(
    [() => form.value.amount, () => form.value.price, () => form.value.fee],
    ([amount, price, fee]) => {
      if (isInitializing.value || !isFund.value || sharesTouched.value) return;
      const next = recalcShares(amount, price, fee);
      if (next == null) return;
      recomputeWriting.value = true;
      form.value.quantity = next;
      nextTick(() => {
        recomputeWriting.value = false;
      });
    }
  );

  // 份额被改动（非初始化、非反算写入窗口）→ 视为用户手改，反算从此让位
  watch(
    () => form.value.quantity,
    () => {
      if (isInitializing.value || recomputeWriting.value) return;
      sharesTouched.value = true;
    }
  );

  // 股票 / 可转债：quantity / price / fee 变化 → 正算 amount
  watch(
    [() => form.value.quantity, () => form.value.price, () => form.value.fee],
    ([quantity, price, fee]) => {
      if (isInitializing.value || isFund.value) return;
      const next = recalcAmount(quantity, price, fee);
      if (next == null) return;
      form.value.amount = next;
    }
  );

  // 核心联动：交易日期变化 → 自动计算确认日期 → 自动拉取净值
  // 统一走 useFundTradeDate composable，与 BuyForm / SellForm 共用同一套逻辑
  watch(
    [() => form.value.trade_date, () => isAfter15.value],
    async ([newDate]) => {
      if (!newDate) {
        confirmDateDisplay.value = "";
        return;
      }

      if (!isFund.value) {
        // 股票 / 可转债：确认日 = 交易日
        form.value.confirm_date = newDate as string;
        confirmDateDisplay.value = "";
        return;
      }

      // 基金：调 composable 计算确认日 + 拉净值
      const code = opts.symbol() || opts.transaction()?.symbol;
      const result = await calcConfirmAndNav({
        tradeDate: newDate as string,
        symbol: code,
        isAfter15: isAfter15.value
      });
      if (result) {
        form.value.confirm_date = result.confirmDate;
        if (result.nav != null) {
          form.value.price = result.nav;
        }
      } else {
        confirmDateDisplay.value = "计算失败";
      }
    }
  );

  async function handleSave() {
    const valid = await formRef.value?.validate().catch(() => false);
    if (!valid) return;

    const t = opts.transaction();
    if (!t?.ledger_id || !t?.id) {
      ElMessage.error("缺少账户或交易信息，无法保存");
      return;
    }
    saving.value = true;
    try {
      const payload = buildUpdatePayload(form.value);
      const res = await updateLedgerTransaction(t.ledger_id, t.id, payload);
      const data = res.data;
      // 保存成功后重置脏基线：否则紧接着的关闭会弹「放弃修改？」，问得毫无意义（#1835）
      markClean();
      // 顺序与原实现一致：先通知父层刷新行数据，再关弹窗
      opts.onSaved(data);
      opts.onClose();
      ElMessage.success("保存成功");
    } catch (e: any) {
      ElMessage.error(e?.message || "保存失败");
    } finally {
      saving.value = false;
    }
  }

  return {
    saving,
    formRef,
    form,
    isAfter15,
    confirmDateDisplay,
    navLoading,
    isManual,
    isFund,
    quantityPrecision,
    quantityStep,
    disabledDate,
    rules,
    initForm,
    resetAfterClose,
    onBeforeClose,
    requestClose,
    handleSave
  };
}
