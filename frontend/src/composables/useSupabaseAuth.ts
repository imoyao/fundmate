import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessageBox, ElMessage } from "element-plus";
import { supabase } from "@/utils/supabase";
import { createWatchlistItem } from "@/api/watchlist";
import { createPosition } from "@/api/positions";
import { POSITION_SOURCE } from "@/constants";
import type { LocalHolding } from "@/composables/useLocalHoldings";
import type { User, Session } from "@supabase/supabase-js";

// 探市观察数据本地键（useLocalHoldings.ts 同源）
const EXPLORE_STORAGE_KEY = "showbuy_explore_v1";
const EXPLORE_MIGRATED_KEY = "showbuy_explore_migrated";

export function useSupabaseAuth() {
  const router = useRouter();
  const user = ref<User | null>(null);
  const session = ref<Session | null>(null);
  const loading = ref(true);
  const isAuthenticated = computed(() => !!user.value);

  // 检查是否有待迁移的探市数据
  const hasPendingExploreData = computed(() => {
    if (!user.value) return false;
    const raw = localStorage.getItem(EXPLORE_STORAGE_KEY);
    if (!raw) return false;
    try {
      const data = JSON.parse(raw);
      return Array.isArray(data) && data.length > 0;
    } catch {
      return false;
    }
  });

  // 注册
  const signUp = async (email: string, password: string, username?: string) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/welcome`,
        data: { username }
      }
    });
    if (error) throw error;
    return data;
  };

  // 登录
  const signIn = async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    if (error) throw error;
    return data;
  };

  // 登出
  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    user.value = null;
    session.value = null;
    router.push("/login");
  };

  // 获取当前会话
  const getSession = async () => {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    session.value = data.session;
    user.value = data.session?.user ?? null;
    return data.session;
  };

  // 初始化认证监听
  const initAuthListener = () => {
    supabase.auth.onAuthStateChange((event, newSession) => {
      session.value = newSession;
      user.value = newSession?.user ?? null;
      loading.value = false;

      // 登录成功后检测待迁移探市数据：弹窗确认（强阻断）后才迁移
      if (event === "SIGNED_IN" && newSession?.user) {
        setTimeout(() => {
          void promptAndMigrateExploreData();
        }, 500);
      }

      // 登出：清理用户会话与迁移标记，换账号登录可重新迁移
      if (event === "SIGNED_OUT") {
        user.value = null;
        session.value = null;
        localStorage.removeItem(EXPLORE_MIGRATED_KEY);
      }
    });
  };

  // 读取本地探市观察数据
  const getExploreHoldings = (): LocalHolding[] => {
    const raw = localStorage.getItem(EXPLORE_STORAGE_KEY);
    if (!raw) return [];
    try {
      const data = JSON.parse(raw);
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  };

  // 弹窗确认（预览资产名称），确认后迁移；取消则保留本地数据
  const promptAndMigrateExploreData = async (): Promise<boolean> => {
    if (!user.value) return false;
    const holdings = getExploreHoldings();
    if (holdings.length === 0) return false;

    const preview = holdings
      .slice(0, 5)
      .map(h => h.name || h.symbol)
      .join("、");
    const more = holdings.length > 5 ? `等 ${holdings.length} 个` : "";

    try {
      await ElMessageBox.confirm(
        `将「${preview}」${more} 资产同步到自选列表「观察中」？迁移后可在主站自选中管理。`,
        "发现探市观察数据",
        {
          confirmButtonText: "迁移",
          cancelButtonText: "暂不",
          type: "info"
        }
      );
    } catch {
      return false;
    }

    try {
      const result = await migrateExploreData(holdings);
      ElMessage.success(
        `已迁移 ${result.imported} 个资产${
          result.skipped > 0 ? `，跳过已存在 ${result.skipped} 个` : ""
        }`
      );
      return true;
    } catch (e) {
      ElMessage.error(`迁移失败：${(e as Error).message || "请稍后重试"}`);
      return false;
    }
  };

  // 迁移探市数据到主站自选（后端 API，观察中状态），成功后才清本地
  const migrateExploreData = async (
    holdings: LocalHolding[]
  ): Promise<{ imported: number; skipped: number }> => {
    if (!user.value) throw new Error("用户未登录");

    let imported = 0;
    let skipped = 0;
    const failed: string[] = [];

    for (const h of holdings) {
      const hasPosition = h.costPrice != null && h.quantity != null;
      try {
        // 1) 始终写入自选（观察状态），保持原迁移行为
        await createWatchlistItem({
          symbol: h.symbol,
          asset_type: h.type,
          venue: h.type === "fund" ? "OTC" : "EXCHANGE",
          add_reason: "探市观察迁移",
          cost_price: h.costPrice ?? undefined,
          quantity: h.quantity ?? undefined
        });
        imported++;

        // 2) 若用户录入了持仓快照（成本+份额），额外写入 positions 表。
        //    source=explore 标明来自探市录入；ledger_id 不传（NULL），
        //    即归入「未归档持仓」，由后端 @validates 约束 source 合法。
        if (hasPosition) {
          await createPosition({
            symbol: h.symbol,
            name: h.name,
            market: "CN_A",
            type: h.type,
            quantity: h.quantity as number,
            avg_price: h.costPrice as number,
            currency: "CNY",
            trade_date: new Date().toISOString().slice(0, 10),
            op_type: "buy",
            source: POSITION_SOURCE.EXPLORE,
            notes: "来自探市页面录入",
            ledger_id: null
          });
        }
      } catch (e: any) {
        // 已在自选中 → 跳过不算失败；其余记入失败
        if (e?.response?.status === 409) {
          skipped++;
        } else {
          failed.push(h.symbol);
        }
      }
    }

    // 有失败则保留本地数据（成功项已在服务端，幂等重试只补失败项）
    if (failed.length > 0) {
      throw new Error(
        `有 ${failed.length} 个资产迁移失败（${failed.join("、")}）`
      );
    }

    localStorage.removeItem(EXPLORE_STORAGE_KEY);
    localStorage.setItem(EXPLORE_MIGRATED_KEY, "true");
    return { imported, skipped };
  };

  // 手动触发迁移（设置抽屉入口）
  const manualMigrate = async (): Promise<{
    imported: number;
    skipped: number;
  }> => {
    if (!user.value) {
      throw new Error("请先登录");
    }
    const holdings = getExploreHoldings();
    if (holdings.length === 0) {
      throw new Error("没有可迁移的数据");
    }
    return migrateExploreData(holdings);
  };

  return {
    user,
    session,
    loading,
    isAuthenticated,
    hasPendingExploreData,
    getExploreHoldings,
    signUp,
    signIn,
    signOut,
    getSession,
    initAuthListener,
    manualMigrate
  };
}
