import App from "./App.vue";
import router from "./router";
import { setupStore } from "@/store";
import { getPlatformConfig } from "./config";
import { MotionPlugin } from "@vueuse/motion";
import { useEcharts } from "@/plugins/echarts";
import { createApp, type Directive } from "vue";
import { useElementPlus } from "@/plugins/elementPlus";
import { injectResponsiveStorage } from "@/utils/responsive";

import Table from "@pureadmin/table";
// import PureDescriptions from "@pureadmin/descriptions";

// 引入重置样式
import "./style/reset.scss";
// 导入公共样式
import "./style/index.scss";
// 导入配色方案
import "./style/colors.css";
// 一定要在main.ts中导入tailwind.css，防止vite每次hmr都会请求src/style/index.scss整体css文件导致热更新慢的问题
import "./style/tailwind.css";
// Element Plus 样式已通过 unplugin-element-plus 按需引入，不再全量加载
// import "element-plus/dist/index.css";
// unplugin-element-plus 对 ElMessage/ElMessageBox/ElNotification 三个命令式组件
// 的样式映射有遗漏（曾误判为"无对应样式文件"），这里显式补全，否则 toast/弹窗
// 退化为 static 定位进入文档流，撑开页面出现多余滚动条。
// 样式文件从 element-plus/theme-chalk 复制到 src/style（裸路径 import 会被
// code-inspector 包裹导致不生效，相对路径才可靠）
import "./style/el-message.css";
import "./style/el-message-box.css";
import "./style/el-notification.css";
import "@/style/theme.scss"; // 确保在 Element Plus 之后加载
// 导入字体图标
import "./assets/iconfont/iconfont.js";
import "./assets/iconfont/iconfont.css";
import { addCollection } from "@iconify/vue";
import { icons as epIcons } from "@iconify-json/ep";
addCollection(epIcons);

const app = createApp(App);

// 自定义指令
import * as directives from "@/directives";
Object.keys(directives).forEach(key => {
  app.directive(key, (directives as { [key: string]: Directive })[key]);
});

// 全局注册@iconify/vue图标库
import {
  IconifyIconOffline,
  IconifyIconOnline,
  FontIcon
} from "./components/ReIcon";
app.component("IconifyIconOffline", IconifyIconOffline);
app.component("IconifyIconOnline", IconifyIconOnline);
app.component("FontIcon", FontIcon);

// 全局注册按钮级别权限组件
import { Auth } from "@/components/ReAuth";
import { Perms } from "@/components/RePerms";
app.component("Auth", Auth);
app.component("Perms", Perms);

// 全局注册vue-tippy
import "tippy.js/dist/tippy.css";
import "tippy.js/themes/light.css";
import VueTippy from "vue-tippy";
app.use(VueTippy);

getPlatformConfig(app).then(async config => {
  setupStore(app);
  app.use(router);
  await router.isReady();
  injectResponsiveStorage(app, config);
  app.use(MotionPlugin).use(useElementPlus).use(Table).use(useEcharts);
  // .use(PureDescriptions)
  app.mount("#app");
});
