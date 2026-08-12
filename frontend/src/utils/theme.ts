/**
 * ============================================================
 * theme.ts
 * 主题切换工具 · 多多贝 设计语言 v2.3.2
 * 功能：亮色/暗色切换、主题色切换、系统偏好检测、持久化
 * 最后更新: 2026-06-27
 * ============================================================
 */

import { getConfig } from "@/config";
import { storageLocal } from "@pureadmin/utils";

/** 主题类型 */
export type ThemeMode = "light" | "dark" | "system";

/** 主题色类型（框架预设 + 多多贝） */
export type ThemeColor =
  | "light"
  | "default"
  | "saucePurple"
  | "pink"
  | "dusk"
  | "volcano"
  | "mingQing"
  | "auroraGreen"
  | "showbuy";

/**
 * 切换整体风格（亮色/暗色/系统）
 * @param mode 'light' | 'dark' | 'system'
 */
export function setThemeMode(mode: ThemeMode): void {
  const html = document.documentElement;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

  // 移除已有类
  html.classList.remove("dark");

  // 根据模式设置
  if (mode === "dark") {
    html.classList.add("dark");
  } else if (mode === "system") {
    if (prefersDark) {
      html.classList.add("dark");
    }
  }
  // light 模式：不做任何操作（默认无 dark 类）

  // 保存到 localStorage
  const storage = storageLocal();
  const layout = (storage.getItem("layout") as Record<string, any>) || {};
  storage.setItem("layout", {
    ...layout,
    overallStyle: mode,
    darkMode: mode === "dark" || (mode === "system" && prefersDark)
  });
}

/**
 * 切换主题色（包括 多多贝 主题）
 * @param color ThemeColor
 */
export function setThemeColor(color: ThemeColor): void {
  const html = document.documentElement;
  html.setAttribute("data-theme", color);

  // 保存到 localStorage
  const storage = storageLocal();
  const layout = (storage.getItem("layout") as Record<string, any>) || {};
  storage.setItem("layout", {
    ...layout,
    themeColor: color,
    theme: color
  });

  // 如果主题色是 showbuy，同步 Element Plus 主色
  if (color === "showbuy") {
    const brandColor = "#E34F38";
    document.documentElement.style.setProperty(
      "--el-color-primary",
      brandColor
    );
    // 通知框架更新 Element Plus 主题色（通过事件）
    window.dispatchEvent(
      new CustomEvent("theme-color-change", { detail: { color: brandColor } })
    );
  }
}

/**
 * 检测系统是否偏好暗色模式
 * @returns boolean
 */
export function isSystemDarkMode(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * 监听系统主题变化
 * @param callback 回调函数
 * @returns 取消监听的函数
 */
export function watchSystemTheme(
  callback: (isDark: boolean) => void
): () => void {
  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

  const handler = (e: MediaQueryListEvent) => {
    callback(e.matches);
  };

  mediaQuery.addEventListener("change", handler);

  // 返回取消监听函数
  return () => {
    mediaQuery.removeEventListener("change", handler);
  };
}

/**
 * 获取当前主题模式
 * @returns ThemeMode
 */
export function getCurrentThemeMode(): ThemeMode {
  const storage = storageLocal();
  const layout = (storage.getItem("layout") as Record<string, any>) || {};
  return (layout?.overallStyle as ThemeMode) || "system";
}

/**
 * 获取当前主题色
 * @returns ThemeColor
 */
export function getCurrentThemeColor(): ThemeColor {
  const storage = storageLocal();
  const layout = (storage.getItem("layout") as Record<string, any>) || {};
  return (
    (layout?.themeColor as ThemeColor) ||
    (getConfig().Theme as ThemeColor) ||
    "showbuy"
  );
}

/**
 * 初始化主题（页面加载时调用）
 */
export function initTheme(): void {
  const mode = getCurrentThemeMode();
  const color = getCurrentThemeColor();

  setThemeMode(mode);
  setThemeColor(color);

  // 如果 mode === 'system'，监听系统变化
  if (mode === "system") {
    watchSystemTheme(isDark => {
      const html = document.documentElement;
      if (isDark) {
        html.classList.add("dark");
      } else {
        html.classList.remove("dark");
      }
      // 更新 storage 中的 darkMode
      const storage = storageLocal();
      const layout = (storage.getItem("layout") as Record<string, any>) || {};
      storage.setItem("layout", {
        ...layout,
        darkMode: isDark
      });
    });
  }
}

/**
 * 在 Vue 组件中使用主题切换的 composable
 */
import { ref, onMounted, onUnmounted, computed } from "vue";

export function useTheme() {
  const currentMode = ref<ThemeMode>(getCurrentThemeMode());
  const currentColor = ref<ThemeColor>(getCurrentThemeColor());
  const isDark = ref(document.documentElement.classList.contains("dark"));

  let unwatch: (() => void) | null = null;

  // 切换到亮色模式
  const setLight = () => {
    currentMode.value = "light";
    setThemeMode("light");
    isDark.value = false;
  };

  // 切换到暗色模式
  const setDark = () => {
    currentMode.value = "dark";
    setThemeMode("dark");
    isDark.value = true;
  };

  // 切换到系统模式
  const setSystem = () => {
    currentMode.value = "system";
    setThemeMode("system");
    isDark.value = isSystemDarkMode();
  };

  // 切换主题色
  const setColor = (color: ThemeColor) => {
    currentColor.value = color;
    setThemeColor(color);
  };

  // 切换亮色/暗色（切换整体风格）
  const toggleThemeMode = () => {
    if (currentMode.value === "light") {
      setDark();
    } else if (currentMode.value === "dark") {
      setLight();
    } else {
      // system 模式下，根据当前实际显示切换
      if (isDark.value) {
        setLight();
      } else {
        setDark();
      }
    }
  };

  // 是否暗色
  const isDarkMode = computed(() => isDark.value);

  // 监听系统主题变化
  onMounted(() => {
    unwatch = watchSystemTheme(dark => {
      if (currentMode.value === "system") {
        isDark.value = dark;
        if (dark) {
          document.documentElement.classList.add("dark");
        } else {
          document.documentElement.classList.remove("dark");
        }
      }
    });
  });

  onUnmounted(() => {
    if (unwatch) unwatch();
  });

  return {
    currentMode,
    currentColor,
    isDarkMode,
    setLight,
    setDark,
    setSystem,
    setColor,
    toggleThemeMode
  };
}
