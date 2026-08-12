// frontend/src/composables/useAuthState.ts
// 共享登录态（单例）：供探市 / 温度计等免登录页面感知登录，登录后隐藏轻量入口并引导到自选页。
// 用模块级单例 ref，保证多个页面/组件读取同一份响应式状态，避免各自订阅产生重复初始化。
import { ref } from "vue";
import { supabase } from "@/utils/supabase";

// 模块级单例状态：首次调用即初始化，后续所有调用共享同一引用
const isAuthenticated = ref(false);
const loading = ref(true);
let initialized = false;

async function init() {
  if (initialized) return;
  initialized = true;
  // 刷新页面已登录：主动拉取会话，保证首次渲染即正确
  try {
    const { data } = await supabase.auth.getSession();
    isAuthenticated.value = !!data.session;
  } catch {
    isAuthenticated.value = false;
  }
  loading.value = false;

  // 运行期登录态变化（登录 / 登出 / token 刷新）同步到单例
  supabase.auth.onAuthStateChange(event => {
    if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
      isAuthenticated.value = true;
    } else if (event === "SIGNED_OUT") {
      isAuthenticated.value = false;
    }
    loading.value = false;
  });
}

export function useAuthState() {
  void init();
  return { isAuthenticated, loading };
}
