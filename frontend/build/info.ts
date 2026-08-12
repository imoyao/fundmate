import type { Plugin } from "vite";
import gradient from "gradient-string";
import { getPackageSize } from "./utils";
import dayjs, { type Dayjs } from "dayjs";
import duration from "dayjs/plugin/duration";
import boxen, { type Options as BoxenOptions } from "boxen";
dayjs.extend(duration);

const welcomeMessage = gradient(["cyan", "magenta"]).multiline(
  `多多贝 · 个人投资记账 / 家庭资产管理平台\n帮你（尤其是使用多账户、多平台购买基金理财产品的朋友）算清真实收益，让复利增长清晰可见\n核心能力：真实收益率（XIRR）、持仓透视、市场温度计（探市）\n\n📚 文档站（在仓库根目录执行）：\n  本地开发  pnpm run docs:dev\n  本地构建  pnpm run docs:build\n\n🌐 远端访问地址：待部署上线后补充`
);

const boxenOptions: BoxenOptions = {
  padding: 0.5,
  borderColor: "cyan",
  borderStyle: "round"
};

export function viteBuildInfo(): Plugin {
  let config: { command: string };
  let startTime: Dayjs;
  let endTime: Dayjs;
  let outDir: string;
  return {
    name: "vite:buildInfo",
    configResolved(resolvedConfig) {
      config = resolvedConfig;
      outDir = resolvedConfig.build?.outDir ?? "dist";
    },
    buildStart() {
      console.log(boxen(welcomeMessage, boxenOptions));
      if (config.command === "build") {
        startTime = dayjs(new Date());
      }
    },
    closeBundle() {
      if (config.command === "build") {
        endTime = dayjs(new Date());
        getPackageSize({
          folder: outDir,
          callback: (size: string) => {
            console.log(
              boxen(
                gradient(["cyan", "magenta"]).multiline(
                  `🎉 恭喜打包完成（总用时${dayjs
                    .duration(endTime.diff(startTime))
                    .format("mm分ss秒")}，打包后的大小为${size}）`
                ),
                boxenOptions
              )
            );
          }
        });
      }
    }
  };
}
