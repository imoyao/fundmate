import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { supabase } from "@/utils/supabase";
import type { User, Session } from "@supabase/supabase-js";

export function useSupabaseAuth() {
  const router = useRouter();
  const user = ref<User | null>(null);
  const session = ref<Session | null>(null);
  const loading = ref(true);
  const isAuthenticated = computed(() => !!user.value);

  // 是否有待迁移的探市数据
  const hasPendingExploreData = computed(() => {
    if (!user.value) return false;
    const raw = localStorage.getItem("showbuy_explore_v1");
    if (!raw) return false;
    try {
      const data = JSON.parse(raw);
      return Array.isArray(data) && data.length > 0;
    } catch {
      return false;
    }
  });

  // 注册
  const signUp = async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/welcome`
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

      // 登录成功后自动检测并迁移探市数据
      if (event === "SIGNED_IN" && newSession?.user) {
        // 延迟执行，确保页面完全加载
        setTimeout(() => {
          checkAndMigrateExploreData();
        }, 500);
      }

      // 登出
      if (event === "SIGNED_OUT") {
        user.value = null;
        session.value = null;
      }
    });
  };

  // 检查并迁移探市数据
  const checkAndMigrateExploreData = async () => {
    const raw = localStorage.getItem("showbuy_explore_v1");
    if (!raw) return;

    let holdings: any[];
    try {
      holdings = JSON.parse(raw);
      if (!Array.isArray(holdings) || holdings.length === 0) return;
    } catch {
      return;
    }

    try {
      await migrateExploreData(holdings);
      localStorage.removeItem("showbuy_explore_v1");
      localStorage.setItem("showbuy_explore_migrated", "true");
      console.log(`✅ 成功迁移 ${holdings.length} 个资产到观察仓`);
    } catch (e) {
      console.error("探市数据迁移失败:", e);
    }
  };

  // 迁移探市数据到 Supabase
  const migrateExploreData = async (holdings: any[]) => {
    const userId = user.value?.id;
    if (!userId) throw new Error("用户未登录");

    // 1. 获取或创建「观察仓」分组
    let groupId = await getOrCreateObservationGroup(userId);

    // 2. 遍历迁移资产
    for (const h of holdings) {
      // 检查是否已存在
      const { data: existing } = await supabase
        .from("watchlist_items")
        .select("id")
        .eq("user_id", userId)
        .eq("symbol", h.symbol)
        .maybeSingle();

      if (existing) continue;

      // 创建自选资产
      const { data: item, error } = await supabase
        .from("watchlist_items")
        .insert({
          user_id: userId,
          symbol: h.symbol,
          name: h.name,
          asset_type: h.type === "fund" ? "fund" : "stock",
          venue: h.type === "fund" ? "OTC" : "EXCHANGE"
        })
        .select()
        .single();

      if (error) {
        console.error("创建资产失败:", h.symbol, error);
        continue;
      }

      if (item) {
        // 关联到「观察仓」分组
        await supabase.from("watchlist_group_items").insert({
          group_id: groupId,
          item_id: item.id
        });
      }
    }
  };

  // 获取或创建「观察仓」分组
  const getOrCreateObservationGroup = async (
    userId: string
  ): Promise<number> => {
    // 查找已有「观察仓」
    const { data: existing } = await supabase
      .from("watchlist_groups")
      .select("id")
      .eq("user_id", userId)
      .eq("group_type", "observation")
      .maybeSingle();

    if (existing) return existing.id;

    // 创建新分组
    const { data: newGroup, error } = await supabase
      .from("watchlist_groups")
      .insert({
        user_id: userId,
        name: "观察仓",
        group_type: "observation",
        is_system: true,
        color: "#81b29a"
      })
      .select()
      .single();

    if (error) throw error;
    return newGroup.id;
  };

  // 获取探市数据（用于迁移弹窗展示）
  const getExploreHoldings = () => {
    const raw = localStorage.getItem("showbuy_explore_v1");
    if (!raw) return [];
    try {
      const data = JSON.parse(raw);
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  };

  // 手动触发迁移
  const manualMigrate = async () => {
    if (!user.value) {
      throw new Error("请先登录");
    }
    const holdings = getExploreHoldings();
    if (holdings.length === 0) {
      throw new Error("没有可迁移的数据");
    }
    await migrateExploreData(holdings);
    localStorage.removeItem("showbuy_explore_v1");
    localStorage.setItem("showbuy_explore_migrated", "true");
    return holdings.length;
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
