// frontend/build/plugins.ts

// 🔥 注释掉 CDN 相关的导入和调用
// import { cdn } from "./cdn";   // 注释或删除
import vue from "@vitejs/plugin-vue";
import { viteBuildInfo } from "./info";
import svgLoader from "vite-svg-loader";
import Icons from "unplugin-icons/vite";
import ElementPlus from "unplugin-element-plus/vite";
import type { PluginOption } from "vite";
import vueJsx from "@vitejs/plugin-vue-jsx";
import tailwindcss from "@tailwindcss/vite";
import { configCompressPlugin } from "./compress";
import removeNoMatch from "vite-plugin-router-warn";
import { visualizer } from "rollup-plugin-visualizer";
import removeConsole from "vite-plugin-remove-console";
import { codeInspectorPlugin } from "code-inspector-plugin";

export function getPluginsList(
  VITE_CDN: boolean,
  VITE_COMPRESSION: ViteCompression
): PluginOption[] {
  const lifecycle = process.env.npm_lifecycle_event;
  return [
    tailwindcss(),
    vue(),
    vueJsx(),
    codeInspectorPlugin({
      bundler: "vite",
      hideConsole: true
    }),
    viteBuildInfo(),
    removeNoMatch(),
    svgLoader(),
    Icons({
      compiler: "vue3",
      scale: 1
    }),
    // Element Plus 样式按需引入（替代全量 import 'element-plus/dist/index.css'）
    ElementPlus({
      ignoreComponents: [
        "TableV2", // ElTableV2 被插件错误映射到 auto-resizer
        "PopoverDirective", // 指令类型，无对应组件样式文件
        "Loading", // 插件服务，无对应组件样式文件
        "InfiniteScroll", // 指令类型，无对应组件样式文件
        // 三个命令式组件 unplugin 不注入样式，已在 main.ts 显式补全
        //（element-plus/theme-chalk/el-{message,message-box,notification}.css）
        "Message",
        "MessageBox",
        "Notification"
      ]
    }),
    // 🔥 完全注释掉 CDN 插件
    // VITE_CDN ? cdn : null,
    configCompressPlugin(VITE_COMPRESSION),
    removeConsole({ external: ["src/assets/iconfont/iconfont.js"] }),
    lifecycle === "report"
      ? visualizer({ open: true, brotliSize: true, filename: "report.html" })
      : (null as any)
  ];
}
