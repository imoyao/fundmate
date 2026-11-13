/**
 * 「类现金管理」弹窗的状态与写路径（账户详情 / 全面盘点 / 搜索命中三处共用）。
 *
 * 只负责编排与请求，不渲染；金额换算、口径说明留在组件里。
 * 写成功后必须 `onChanged()`：归置会改变 `summary` 的孤儿净额桶，
 * 页面上的「类现金合计 / 总资产」是缓存值，不刷新就是旧数。
 */
import { ref, type Ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createCashLikeFlow,
  deleteCashLikeFlow,
  getCashLikeFlows,
  getCashLikeTargets,
  reconcileCashLikeFlows,
  updateCashLikeFlow,
  type CashLikeCreateInput,
  type CashLikeFlow,
  type CashLikeTarget,
  type CashLikeUpdateInput
} from "@/api/cashLike";

const PER_PAGE = 20;

export function useCashLikeManage(
  ledgerId: Ref<number | null>,
  onChanged?: () => void
) {
  const visible = ref(false);
  const loading = ref(false);
  const submitting = ref(false);
  const flows = ref<CashLikeFlow[]>([]);
  const targets = ref<CashLikeTarget[]>([]);
  const total = ref(0);
  const page = ref(1);
  const query = ref("");
  const includeReconciled = ref(false);
  const selectedIds = ref<number[]>([]);
  const formVisible = ref(false);
  const editing = ref<CashLikeFlow | null>(null);
  const reconcileVisible = ref(false);
  const reconcileAction = ref<"attach" | "detach">("attach");
  const targetId = ref<number | null>(null);
  const targetQuery = ref("");

  async function load() {
    loading.value = true;
    try {
      const res = await getCashLikeFlows({
        ledger_id: ledgerId.value ?? undefined,
        q: query.value.trim() || undefined,
        include_reconciled: includeReconciled.value,
        page: page.value,
        per_page: PER_PAGE
      });
      flows.value = res?.data?.items ?? [];
      total.value = res?.data?.total ?? 0;
    } catch (e) {
      ElMessage.error(errorText(e, "加载账外流水失败"));
      flows.value = [];
      total.value = 0;
    } finally {
      loading.value = false;
    }
  }

  async function loadTargets() {
    try {
      const res = await getCashLikeTargets({
        ledger_id: ledgerId.value ?? undefined,
        q: targetQuery.value.trim() || undefined
      });
      targets.value = res?.data?.items ?? [];
    } catch (e) {
      ElMessage.error(errorText(e, "加载可归置持仓失败"));
      targets.value = [];
    }
  }

  async function open(seedQuery = "") {
    query.value = seedQuery;
    page.value = 1;
    selectedIds.value = [];
    visible.value = true;
    await Promise.all([load(), loadTargets()]);
  }

  function close() {
    visible.value = false;
    formVisible.value = false;
    reconcileVisible.value = false;
  }

  function openCreate() {
    editing.value = null;
    formVisible.value = true;
  }

  function openEdit(flow: CashLikeFlow) {
    if (flow.reconciled) {
      ElMessage.warning("该流水已归置到持仓，请先撤销归置再编辑");
      return;
    }
    editing.value = flow;
    formVisible.value = true;
  }

  async function submitCreate(
    input: Omit<CashLikeCreateInput, "client_token">
  ) {
    submitting.value = true;
    try {
      await createCashLikeFlow({ ...input, client_token: crypto.randomUUID() });
      ElMessage.success(
        input.kind === "repayment" ? "到期回款已补录" : "流水已补录"
      );
      formVisible.value = false;
      await load();
      onChanged?.();
    } catch (e) {
      ElMessage.error(errorText(e, "补录失败"));
    } finally {
      submitting.value = false;
    }
  }

  async function submitEdit(id: number, input: CashLikeUpdateInput) {
    submitting.value = true;
    try {
      await updateCashLikeFlow(id, input);
      ElMessage.success("流水已更新");
      formVisible.value = false;
      await load();
      onChanged?.();
    } catch (e) {
      ElMessage.error(errorText(e, "更新失败"));
    } finally {
      submitting.value = false;
    }
  }

  async function remove(flow: CashLikeFlow) {
    if (flow.reconciled) {
      ElMessage.warning("该流水已归置到持仓，请先撤销归置再删除");
      return;
    }
    try {
      await ElMessageBox.confirm(
        `确认删除「${flow.position_name || "未命名"}」这笔账外流水？`,
        "删除确认",
        { type: "warning" }
      );
    } catch {
      return;
    }
    await deleteCashLikeFlow(flow.id);
    ElMessage.success("已删除");
    await load();
    onChanged?.();
  }

  function openReconcile(action: "attach" | "detach") {
    if (selectedIds.value.length === 0) {
      ElMessage.warning("请先选择流水");
      return;
    }
    if (action === "attach" && targets.value.length === 0) {
      ElMessage.warning("当前账户下没有可归置的持仓");
      return;
    }
    targetId.value = null;
    reconcileVisible.value = true;
    reconcileAction.value = action;
  }

  async function submitReconcile() {
    if (reconcileAction.value === "attach" && !targetId.value) {
      ElMessage.warning("请选择目标持仓");
      return;
    }
    submitting.value = true;
    try {
      await reconcileCashLikeFlows({
        action: reconcileAction.value,
        transaction_ids: selectedIds.value,
        target_position_id: targetId.value ?? undefined
      });
      ElMessage.success(
        reconcileAction.value === "attach"
          ? "已归置：这批流水不再单独计入类现金"
          : "已撤销归置：流水重回账外类现金"
      );
      reconcileVisible.value = false;
      selectedIds.value = [];
      await load();
      onChanged?.();
    } catch (e) {
      ElMessage.error(errorText(e, "归置失败"));
    } finally {
      submitting.value = false;
    }
  }

  return {
    visible,
    loading,
    submitting,
    flows,
    targets,
    total,
    page,
    query,
    includeReconciled,
    selectedIds,
    formVisible,
    editing,
    reconcileVisible,
    reconcileAction,
    targetId,
    targetQuery,
    perPage: PER_PAGE,
    load,
    loadTargets,
    open,
    close,
    openCreate,
    openEdit,
    submitCreate,
    submitEdit,
    remove,
    openReconcile,
    submitReconcile
  };
}

function errorText(e: unknown, fallback: string): string {
  const err = e as {
    response?: { data?: { message?: string } };
    message?: string;
  };
  return err?.response?.data?.message || err?.message || fallback;
}
