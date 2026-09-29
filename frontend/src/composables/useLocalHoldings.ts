// frontend/src/composables/useLocalHoldings.ts
import { ref, computed } from "vue";
import { useAuthState } from "@/composables/useAuthState";

const STORAGE_KEY = "showbuy_explore_v1";
const MAX_HOLDINGS = 50;

export interface LocalHolding {
  id: string;
  symbol: string;
  name: string;
  type: "stock" | "fund" | "etf";
  costPrice: number | null; // null 表示未填 → 纯观察模式
  quantity: number | null; // null 表示未填 → 纯观察模式
  addedAt: string; // ISO 字符串，用于迁移时透传
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 6);
}

function readStorage(): LocalHolding[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    // 简单校验：必须是数组
    if (!Array.isArray(data)) return [];
    return data;
  } catch {
    return [];
  }
}

function writeStorage(data: LocalHolding[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

// 模块级单例持仓：跨组件 / 跨调用共享同一份响应式状态，是 B11 跨 tab 同步的基础
const holdings = ref<LocalHolding[]>(readStorage());
let storageSyncAttached = false;

// 跨 tab 同步（B11）：其他 tab 写入 localStorage 时，本 tab 重新读入并刷新 UI。
// storage 事件只在同一 key 被「其他文档」改写时触发，本 tab 自身改写不会触发，符合预期。
function attachCrossTabSync(): void {
  if (storageSyncAttached) return;
  storageSyncAttached = true;
  if (typeof window === "undefined" || !window.addEventListener) return;
  window.addEventListener("storage", (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === null) {
      holdings.value = readStorage();
    }
  });
}

export function useLocalHoldings() {
  attachCrossTabSync();
  const { isAuthenticated } = useAuthState();

  const addHolding = (
    data: Omit<LocalHolding, "id" | "addedAt">
  ): { success: boolean; message?: string } => {
    // 检查是否已存在
    const exists = holdings.value.some(h => h.symbol === data.symbol);
    if (exists) {
      return { success: false, message: `「${data.symbol}」已在观察列表中` };
    }

    // B12：本地 50 上限只约束未注册游客；注册用户数据可迁移到后端自选，
    // 不再受本地上限限制，故不再提示「注册后可解锁更多」（注册后自动解除）。
    if (!isAuthenticated.value && holdings.value.length >= MAX_HOLDINGS) {
      return {
        success: false,
        message: `观察列表已达上限（${MAX_HOLDINGS}个），注册后可解锁更多`
      };
    }

    const newItem: LocalHolding = {
      ...data,
      id: generateId(),
      addedAt: new Date().toISOString()
    };

    holdings.value = [...holdings.value, newItem];
    writeStorage(holdings.value);
    return { success: true };
  };

  const removeHolding = (id: string): void => {
    holdings.value = holdings.value.filter(h => h.id !== id);
    writeStorage(holdings.value);
  };

  const updateHolding = (
    id: string,
    updates: Partial<Pick<LocalHolding, "costPrice" | "quantity">>
  ): void => {
    holdings.value = holdings.value.map(h =>
      h.id === id ? { ...h, ...updates } : h
    );
    writeStorage(holdings.value);
  };

  const clearAll = (): void => {
    holdings.value = [];
    writeStorage(holdings.value);
  };

  // 供 useRealtimeQuotes 注入的适配器
  const getHoldingsForQuotes = () => {
    return holdings.value.map(h => ({
      symbol: h.symbol,
      name: h.name,
      type: h.type,
      costPrice: h.costPrice ?? undefined,
      quantity: h.quantity ?? undefined
    }));
  };

  // 判断是否处于“纯观察模式”：所有资产均未填成本或份额
  const isPureObservationMode = computed(() => {
    if (holdings.value.length === 0) return false;
    return holdings.value.every(
      h => h.costPrice === null || h.quantity === null
    );
  });

  // 获取总数量
  const totalCount = computed(() => holdings.value.length);

  return {
    holdings,
    addHolding,
    removeHolding,
    updateHolding,
    clearAll,
    getHoldingsForQuotes,
    isPureObservationMode,
    totalCount
  };
}
