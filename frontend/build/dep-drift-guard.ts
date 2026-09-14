// frontend/build/dep-drift-guard.ts
//
// 背景（Issue #972：dev server 版本错位）
//   `pnpm up` / `pnpm install` 会改写磁盘上的 node_modules 与锁文件，
//   但**已在运行的 vite dev server 仍持有旧模块的缓存与依赖预构建产物**。
//   此时 HMR 会把新旧版本混在一起，表现为「CSS/组件样式莫名错乱」「改了没生效」，
//   极易被误判成业务代码 bug（历史上就误判过暗黑模式，见 #976）。
//
// 做法
//   监听锁文件与 package.json；一旦变更，调用 ViteDevServer.restart(true)
//   重建模块图并重新预构建依赖，让 dev server 回到与磁盘一致的状态。
//   restart 属较新的内部能力，故做能力探测 + try/catch：不可用或失败时
//   退化为「醒目告警 + 要求手动重启」，绝不因本插件阻断开发。
//
// 关闭方式：DISABLE_DEP_DRIFT_GUARD=1 pnpm dev

import { existsSync } from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

/** 依赖变更的信号文件：锁文件优先，package.json 兜底（手动改版本但未重新锁的情况） */
const WATCHED_FILES = [
  "pnpm-lock.yaml",
  "package.json",
  "package-lock.yaml",
  "yarn.lock"
];

/** pnpm / 编辑器可能连续多次写入，去抖避免重复重启 */
const DEBOUNCE_MS = 300;

const MANUAL_HINT =
  "请手动重启 dev server（Ctrl+C 后重新 pnpm dev），否则会继续加载旧版本模块。";

export function depDriftGuard(): Plugin {
  return {
    name: "fundmate:dep-drift-guard",
    configureServer(server) {
      if (process.env.DISABLE_DEP_DRIFT_GUARD === "1") {
        server.config.logger.info("[dep-drift-guard] 已通过环境变量关闭");
        return;
      }

      const logger = server.config.logger;
      const root = server.config.root;

      // 只监听真实存在的文件，避免 chokidar 对不存在的路径告警
      const watched = new Set<string>();
      for (const f of WATCHED_FILES) {
        const abs = path.resolve(root, f);
        if (existsSync(abs)) watched.add(abs);
      }
      if (watched.size === 0) return;

      let timer: ReturnType<typeof setTimeout> | null = null;
      let restarting = false;

      const trigger = (file: string) => {
        if (restarting) return;
        if (timer) clearTimeout(timer);
        timer = setTimeout(async () => {
          restarting = true;
          logger.warn(
            `\n[dep-drift-guard] 检测到依赖清单变化：${path.basename(file)}\n` +
              "  磁盘上的 node_modules 已与运行中的 dev server 不一致，正在自动重启以重新加载。\n"
          );
          try {
            if (typeof server.restart === "function") {
              await server.restart(true);
              logger.info(
                "[dep-drift-guard] dev server 已重启，模块图与依赖预构建已按磁盘新版本重建。\n"
              );
            } else {
              logger.warn(
                `[dep-drift-guard] 当前 vite 版本不支持自动重启（server.restart 缺失）。${MANUAL_HINT}\n`
              );
            }
          } catch (err) {
            logger.error(
              `[dep-drift-guard] 自动重启失败：${
                err instanceof Error ? err.message : String(err)
              }\n  ${MANUAL_HINT}\n`
            );
          } finally {
            restarting = false;
          }
        }, DEBOUNCE_MS);
      };

      // chokidar 默认忽略 node_modules，且不会主动监听根目录锁文件，需显式加入
      server.watcher.add([...watched]);
      server.watcher.on("change", (file: string) => {
        if (watched.has(path.resolve(file))) trigger(file);
      });
    }
  };
}
