<!--
  外观设置面板（#980 拆分）

  六个区块已拆到 `sections/`（整体风格 / 主题色 / 导航模式 / 页宽 / 页签风格 /
  界面显示），纯下标与色值计算在 `sections/settingModel.ts`。

  **状态仍然全部留在这一层**：`useDataThemeChange()` 每次调用都会新建
  `dataTheme` / `overallStyle` 两个 ref（只有 `layoutTheme` / `layout` 是基于
  `$storage` 的共享 computed），子组件各自调一份会拿到互不同步的副本——所以
  子组件一律是「props 进、emit 出」的展示件，不自带状态。
-->
<script setup lang="ts">
import {
  ref,
  unref,
  reactive,
  computed,
  nextTick,
  onUnmounted,
  onBeforeMount
} from "vue";
import { emitter } from "@/utils/mitt";
import LayPanel from "../lay-panel/index.vue";
import { useNav } from "@/layout/hooks/useNav";
import { useAppStoreHook } from "@/store/modules/app";
import { useMultiTagsStoreHook } from "@/store/modules/multiTags";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";
import { useDark, useGlobal } from "@pureadmin/utils";
import type { OptionsType } from "@/components/ReSegmented";
import type { ThemeStyleOption } from "./sections/settingModel";
import AppearanceSection from "./sections/AppearanceSection.vue";
import ThemeColorSection from "./sections/ThemeColorSection.vue";
import NavModeSection from "./sections/NavModeSection.vue";
import PageWidthSection from "./sections/PageWidthSection.vue";
import TabStyleSection from "./sections/TabStyleSection.vue";
import DisplaySection from "./sections/DisplaySection.vue";

const { device } = useNav();
const { isDark } = useDark();
const { $storage } = useGlobal<GlobalPropertiesApi>();

const {
  dataTheme,
  overallStyle,
  layoutTheme,
  themeColors,
  toggleClass,
  dataThemeChange,
  setLayoutThemeColor
} = useDataThemeChange();

/* body添加layout属性，作用于src/style/sidebar.scss */
if (unref(layoutTheme)) {
  const layout = unref(layoutTheme).layout;
  const theme = unref(layoutTheme).theme;
  document.documentElement.setAttribute("data-theme", theme);
  setLayoutModel(layout);
}

/** 默认灵动模式 */
const markValue = ref($storage.configure?.showModel ?? "smart");

const logoVal = ref($storage.configure?.showLogo ?? true);

const settings = reactive({
  greyVal: $storage.configure.grey,
  weakVal: $storage.configure.weak,
  tabsVal: $storage.configure.hideTabs,
  showLogo: $storage.configure.showLogo,
  showModel: $storage.configure.showModel,
  hideFooter: $storage.configure.hideFooter,
  multiTagsCache: $storage.configure.multiTagsCache,
  stretch: $storage.configure.stretch
});

function storageConfigureChange<T>(key: string, val: T): void {
  const storageConfigure = $storage.configure;
  storageConfigure[key] = val;
  $storage.configure = storageConfigure;
}

/** 灰色模式设置 */
const greyChange = (value): void => {
  const htmlEl = document.querySelector("html");
  toggleClass(settings.greyVal, "html-grey", htmlEl);
  storageConfigureChange("grey", value);
};

/** 色弱模式设置 */
const weekChange = (value): void => {
  const htmlEl = document.querySelector("html");
  toggleClass(settings.weakVal, "html-weakness", htmlEl);
  storageConfigureChange("weak", value);
};

/** 隐藏标签页设置 */
const tagsChange = () => {
  const showVal = settings.tabsVal;
  storageConfigureChange("hideTabs", showVal);
  emitter.emit("tagViewsChange", showVal as unknown as string);
};

/** 隐藏页脚设置 */
const hideFooterChange = () => {
  const hideFooter = settings.hideFooter;
  storageConfigureChange("hideFooter", hideFooter);
};

/** 标签页持久化设置 */
const multiTagsCacheChange = () => {
  const multiTagsCache = settings.multiTagsCache;
  storageConfigureChange("multiTagsCache", multiTagsCache);
  useMultiTagsStoreHook().multiTagsCacheChange(multiTagsCache);
};

function onChange(option: OptionsType) {
  const { value } = option;
  markValue.value = value;
  storageConfigureChange("showModel", value);
  emitter.emit("tagViewsShowModel", value);
}

/** 侧边栏Logo */
function logoChange() {
  unref(logoVal)
    ? storageConfigureChange("showLogo", true)
    : storageConfigureChange("showLogo", false);
  emitter.emit("logoChange", unref(logoVal));
}

/** 页宽 */
const setStretch = value => {
  settings.stretch = value;
  storageConfigureChange("stretch", value);
};

/** 设置导航模式 */
function setLayoutModel(layout: string) {
  layoutTheme.value.layout = layout;
  window.document.body.setAttribute("layout", layout);
  $storage.layout = {
    layout,
    theme: layoutTheme.value.theme,
    darkMode: $storage.layout?.darkMode,
    sidebarStatus: $storage.layout?.sidebarStatus,
    epThemeColor: $storage.layout?.epThemeColor,
    themeColor: $storage.layout?.themeColor,
    overallStyle: $storage.layout?.overallStyle
  };
  useAppStoreHook().setLayout(layout);
}

const mediaQueryList = window.matchMedia("(prefers-color-scheme: dark)");

/** 根据操作系统主题设置平台整体风格 */
function updateTheme() {
  if (overallStyle.value !== "system") return;
  if (mediaQueryList.matches) {
    dataTheme.value = true;
  } else {
    dataTheme.value = false;
  }
  dataThemeChange(overallStyle.value);
}

function removeMatchMedia() {
  mediaQueryList.removeEventListener("change", updateTheme);
}

/** 监听操作系统主题改变 */
function watchSystemThemeChange() {
  updateTheme();
  removeMatchMedia();
  mediaQueryList.addEventListener("change", updateTheme);
}

/** 整体风格切换：`自动` 档要接上系统主题监听，其余档只落存储 */
function onOverallStyleChange({
  index,
  option
}: {
  index: number;
  option: ThemeStyleOption;
}) {
  dataTheme.value = index === 1;
  overallStyle.value = option.theme;
  dataThemeChange(option.theme);
  if (index === 2) watchSystemThemeChange();
}

onBeforeMount(() => {
  /* 初始化外观配置 */
  nextTick(() => {
    watchSystemThemeChange();
    settings.greyVal &&
      document.querySelector("html")?.classList.add("html-grey");
    settings.weakVal &&
      document.querySelector("html")?.classList.add("html-weakness");
    settings.tabsVal && tagsChange();
    settings.hideFooter && hideFooterChange();
  });
});

onUnmounted(() => removeMatchMedia);

/** 窄屏（≤1280）不提供页宽设置：那点余量拉伸不出可感知的差异 */
const showPageWidth = computed(() => useAppStoreHook().getViewportWidth > 1280);
</script>

<template>
  <LayPanel>
    <div class="p-5">
      <AppearanceSection
        :overall-style="overallStyle"
        :data-theme="dataTheme"
        :is-dark="isDark"
        @change="onOverallStyleChange"
      />

      <ThemeColorSection
        :colors="themeColors"
        :active-theme="layoutTheme.theme"
        :is-dark="isDark"
        @select="setLayoutThemeColor"
      />

      <NavModeSection
        :layout="layoutTheme.layout"
        :device="device"
        @select="setLayoutModel"
      />

      <PageWidthSection
        v-if="showPageWidth"
        :stretch="settings.stretch"
        @update:stretch="value => (settings.stretch = value)"
        @commit="setStretch"
      />

      <TabStyleSection :mark-value="markValue" @change="onChange" />

      <DisplaySection
        v-model:grey="settings.greyVal"
        v-model:weak="settings.weakVal"
        v-model:hide-tabs="settings.tabsVal"
        v-model:hide-footer="settings.hideFooter"
        v-model:logo="logoVal"
        v-model:multi-tags-cache="settings.multiTagsCache"
        @grey-change="greyChange(settings.greyVal)"
        @weak-change="weekChange(settings.weakVal)"
        @tabs-change="tagsChange"
        @hide-footer-change="hideFooterChange"
        @logo-change="logoChange"
        @multi-tags-cache-change="multiTagsCacheChange"
      />
    </div>
  </LayPanel>
</template>

<style lang="scss" scoped>
:deep(.el-divider__text) {
  font-size: var(--text-body);
  font-weight: 700;
}

/* 开关是 `DisplaySection` 的内部元素，但 `:deep()` 编译成
   `[data-v-本组件] .el-switch__core` —— 子组件**根节点**带本组件的 scopeId，
   后代选择器照样匹配得上，所以这两条可以留在父层 */
:deep(.el-switch__core) {
  --el-switch-off-color: var(--pure-switch-off-color);

  min-width: 36px;
  height: 18px;
}

:deep(.el-switch__core .el-switch__action) {
  height: 14px;
}
</style>
