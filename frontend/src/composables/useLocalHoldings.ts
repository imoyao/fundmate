// frontend/src/composables/useLocalHoldings.ts
import { ref, computed } from "vue";

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

export function useLocalHoldings() {
  const holdings = ref<LocalHolding[]>(readStorage());

  const addHolding = (
    data: Omit<LocalHolding, "id" | "addedAt">
  ): { success: boolean; message?: string } => {
    // 检查是否已存在
    const exists = holdings.value.some(h => h.symbol === data.symbol);
    if (exists) {
      return { success: false, message: `「${data.symbol}」已在观察列表中` };
    }

    if (holdings.value.length >= MAX_HOLDINGS) {
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
