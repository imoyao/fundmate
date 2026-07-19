import { cdnImport } from "fast-vite-plugins";
/**
 * @description 打包时采用`cdn`模式，仅限外网使用（默认不采用，如果需要采用cdn模式，请在 .env.production 文件，将 VITE_CDN 设置成true）
 * 平台采用国内cdn：https://www.bootcdn.cn，当然你也可以选择 https://unpkg.com 或者 https://www.jsdelivr.com
 * 注意：上面提到的仅限外网使用也不是完全肯定的，如果你们公司内网部署的有相关js、css文件，也可以将下面配置对应改一下，整一套内网版cdn
 */
export const cdn = cdnImport({
  // CDN 地址模板（保持和原来一致）
  prodUrl: "https://cdn.bootcdn.net/ajax/libs/{name}/{version}/{path}",
  modules: [
    {
      name: "vue",
      var: "Vue",
      path: "vue.global.prod.min.js"
    },
    {
      name: "vue-router",
      var: "VueRouter",
      path: "vue-router.global.min.js"
    },
    // vue-demi 在 pnpm 下可能仍有问题，尝试移除或保留
    // 如果仍然报错，可以注释掉这一条
    {
      name: "vue-demi",
      var: "VueDemi",
      path: "index.iife.min.js"
    },
    {
      name: "pinia",
      var: "Pinia",
      path: "pinia.iife.min.js"
    },
    {
      name: "element-plus",
      var: "ElementPlus",
      path: "index.full.min.js",
      css: "index.min.css"
    },
    {
      name: "axios",
      var: "axios",
      path: "axios.min.js"
    },
    {
      name: "dayjs",
      var: "dayjs",
      path: "dayjs.min.js"
    },
    {
      name: "echarts",
      var: "echarts",
      path: "echarts.min.js"
    }
  ]
});
