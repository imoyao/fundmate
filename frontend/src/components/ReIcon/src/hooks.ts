import type { iconType } from "./types";
import { h, defineComponent, type Component } from "vue";
import { FontIcon, IconifyIconOnline, IconifyIconOffline } from "../index";

/**
 * 支持 `iconfont`、自定义 `svg` 以及 `iconify` 中所有的图标
 * @see 点击查看文档图标篇 {@link https://pure-admin.cn/pages/icon/}
 * @param icon 必传 图标（字符串 / 组件 / 图标对象；入口按 unknown 逐支收窄）
 * @param attrs 可选 iconType 属性
 * @returns Component
 */
export function useRenderIcon(icon: unknown, attrs?: iconType): Component {
  // iconfont
  const ifReg = /^IF-/;
  const iconProps = { ...attrs };
  // typeof icon === "function" 属于SVG
  if (typeof icon === "string" && ifReg.test(icon)) {
    // iconfont
    const name = icon.split(ifReg)[1];
    const iconName = name.slice(
      0,
      name.indexOf(" ") == -1 ? name.length : name.indexOf(" ")
    );
    const iconType = name.slice(name.indexOf(" ") + 1, name.length);
    return defineComponent({
      name: "FontIcon",
      render() {
        return h(FontIcon, {
          icon: iconName,
          iconType,
          ...iconProps
        });
      }
    });
  } else if (
    typeof icon === "function" ||
    (typeof icon === "object" &&
      icon !== null &&
      typeof (icon as { render?: unknown }).render === "function")
  ) {
    // svg：函数组件或带 render 的组件对象，交给 h 前在唯一边界收窄
    const component = icon as Component;
    return attrs ? h(component, iconProps) : component;
  } else if (typeof icon === "object" && icon !== null) {
    return defineComponent({
      name: "OfflineIcon",
      render() {
        return h(IconifyIconOffline, {
          icon,
          ...iconProps
        });
      }
    });
  } else {
    // 通过是否存在 : 符号来判断是在线还是本地图标，存在即是在线图标，反之
    const iconName = typeof icon === "string" ? icon : "";
    return defineComponent({
      name: "Icon",
      render() {
        if (!iconName) return;
        const IconifyIcon = iconName.includes(":")
          ? IconifyIconOnline
          : IconifyIconOffline;
        return h(IconifyIcon, {
          icon: iconName,
          ...iconProps
        });
      }
    });
  }
}
