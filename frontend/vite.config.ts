import { getPluginsList } from "./build/plugins";
import { include, exclude } from "./build/optimize";
import { type UserConfigExport, type ConfigEnv, loadEnv } from "vite";
import {
  root,
  alias,
  wrapperEnv,
  pathResolve,
  __APP_INFO__
} from "./build/utils";

export default ({ mode }: ConfigEnv): UserConfigExport => {

  const { VITE_CDN, VITE_PORT, VITE_COMPRESSION, VITE_PUBLIC_PATH } =
    wrapperEnv(loadEnv(mode, root));
  return {
    base: VITE_PUBLIC_PATH,
    root,
    resolve: {
      alias
    },
    // 服务端渲染
    server: {
      // 端口号
      port: VITE_PORT,
      host: "0.0.0.0",
      // 本地跨域代理 https://cn.vitejs.dev/config/server-options.html#server-proxy
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000", // 后端地址
          changeOrigin: true,
          // 如果后端没有 /api 前缀，可以 rewrite 去掉
          // rewrite: (path) => path.replace(/^\/api/, '')
        },
      },
      // 预热文件以提前转换和缓存结果，降低启动期间的初始页面加载时长并防止转换瀑布
      warmup: {
        clientFiles: ["./index.html", "./src/{views,components}/*"]
      }
    },
    plugins: getPluginsList(VITE_CDN, VITE_COMPRESSION),
    // https://cn.vitejs.dev/config/dep-optimization-options.html#dep-optimization-options
    optimizeDeps: {
      include,
      exclude
    },
    build: {
      // https://cn.vitejs.dev/guide/build.html#browser-compatibility
      target: "es2015",
      sourcemap: false,
      // 消除打包大小超过500kb警告
      chunkSizeWarningLimit: 4000,
      rollupOptions: {
        input: {
          index: pathResolve("./index.html", import.meta.url)
        },
        // 静态资源分类打包
        output: {
          chunkFileNames: "static/js/[name]-[hash].js",
          entryFileNames: "static/js/[name]-[hash].js",
          assetFileNames: "static/[ext]/[name]-[hash].[ext]",
          // 手动分包：将大依赖独立拆分，降低 Rollup 合并阶段内存峰值
          manualChunks: {
            // Vue 生态核心
            vue: ["vue", "vue-router", "pinia", "@vueuse/core", "@vueuse/motion"],
            // Element Plus UI 框架
            elementPlus: ["element-plus", "@element-plus/icons-vue"],
            // ECharts 图表库（按需引入后体积减小，但仍独立分包）
            echarts: ["echarts", "vue-echarts"],
            // PureAdmin 表格/描述组件
            pureAdmin: ["@pureadmin/table", "@pureadmin/utils"],
            // 工具库集合
            utils: ["axios", "dayjs", "qs", "mitt", "js-cookie", "pinyin-pro", "sortablejs", "localforage", "nprogress"],
          }
        }
      }
    },
    define: {
      __INTLIFY_PROD_DEVTOOLS__: false,
      __APP_INFO__: JSON.stringify(__APP_INFO__)
    }
  };
};
