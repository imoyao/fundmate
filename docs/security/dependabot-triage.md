# Dependabot 漏洞告警处置清单（2026-08-10）

> 背景：用户选 B 方案——拉全量 Dependabot alert，筛出实际未修复的 critical/high，对照 `pdm.lock` / `pnpm-lock.yaml` 实际解析版本 + 代码 import 情况判定真伪。

## 一、总览

- 远端 open alert 总数：**88**
- 按 manifest 分布：
  - `backend/requirements/base.txt`（已删除的旧文件）：**73** ← 全部过期残留
  - 根 `pnpm-lock.yaml`：**12**
  - `frontend/pnpm-lock.yaml`：**3**

## 二、后端 pip（73 个，全部 dismiss）

`dependabot.yml` 的 pip `directory` 已正确指向 `/backend`，但 Dependabot 仍残留基于已删除的 `backend/requirements/base.txt` 的历史扫描结果，不会自动清除。

- `pdm.lock` 实际解析版本全部 ≥ patched 版本：certifi 2026.7.22 / fonttools 4.63.0 / lxml 6.1.1 / pillow 12.3.0 / pyjwt 2.13.0 / soupsieve 2.9.1 / urllib3 2.7.0 / xalpha 0.12.4(git)
- `gevent` / `pymysql` / `Mako` / `virtualenv`：根本不在 `pdm.lock` 里，纯误报，代码也无 import

**处置**：在 GitHub Security → Dependabot alerts 批量 dismiss 这 73 个，reason 选 "This vulnerability is not in my codebase / no longer present"。

编号清单见同目录 `da_phantom_ids.txt`（一行一个）。

## 三、前端 npm（15 个，分两类）

### 3.1 评估后结论：全部 dismiss，不升级（dev-only / 不可达 / patched 不可满足）

2026-08-10 实测：`pnpm update` / `pnpm up` 对这 5 个包均报 "Already up to date"——它们是**传递依赖**，受上游直接依赖的 semver 范围锁死，pnpm 不会强行跨范围升级。逐一核对 npm registry 真实版本后：

| 包 | 当前 lock 版本 | alert patched | npm 真实最新 | 能否安全升 | 结论 |
|---|---|---|---|---|---|
| nanoid | 3.3.16 | 3.3.17 | 6.0.1 | patched 3.3.17 未发布(3.x 最新即 3.3.16)；升 6.x 是破坏性大版本，会崩上游 API | dismiss |
| postcss | 8.5.19 | 8.5.23 | 8.5.26 | 可升到 8.5.26，但仅 dev CSS 处理，不可达 | dismiss（或可选 overrides 钉 8.5.26，低风险） |
| esbuild | 0.21.5 | 0.25.0/0.28.1 | 0.28.2 | 可升，但仅 dev 构建期打包，不可达 | dismiss |
| brace-expansion | 1.1.16 | 1.1.18 | 5.0.9 | lock 内已有 1.1.18 实例；1.1.16 受上游范围约束，强行升 5.x 破坏性 | dismiss |
| js-yaml | 3.15.0 | 3.15.1 | 5.2.3 | 3.15.1 未发布(3.x 已停更)；升 5.x 破坏性大版本 | dismiss |

**关键判断**：这 15 个 npm alert 无一在生产运行时可达（全是 dev/build 工具链传递依赖，不进前端打包产物）。且 patched 版本要么未发布、要么需破坏性大版本跳跃（会搞崩上游包）。强行用 pnpm overrides 覆盖传递依赖风险 > 收益。

处置：15 个 npm alert 全部 dismiss，理由 "This vulnerability is not in my codebase / not reachable in production"（dev-toolchain only）。

### 3.2 明细（15 个 npm alert 编号）

根 `pnpm-lock.yaml`：825/824/823 image-size、822 nanoid、821 js-yaml、820/819 vite(6.x CVE,5.x不受影响)、818 vite、817 postcss、816/812 brace-expansion、732 esbuild、709 trim
frontend `pnpm-lock.yaml`：815 esbuild、627 esbuild、822 nanoid（已在根列，frontend 实例同号）

## 四、执行顺序建议

1. **dismiss 73 个 pip 过期 alert**（da_phantom_ids.txt）—— 立即消除噪声
2. **dismiss 15 个 npm alert**（明细见 3.2）—— dev 工具链不可达 / patched 不可满足
3. 验证：`gh api` 重拉 alert 总数应趋近 0 open

> 注：本地 `pnpm update` / `pnpm up` 实测对这 5 个传递依赖无效（受上游 semver 范围锁死，报 "Already up to date"），且强行 override 有破坏性风险，故不升级、走 dismiss。

## 五、根因与长期建议

`dependabot.yml` 配置本身正确（pip→/backend、npm→/ 与 /frontend、docker、github-actions 均已覆盖）。当前 73 个幽灵告警源于历史 manifest 删除后 Dependabot 不自动清旧记录，**非配置问题，无需改 dependabot.yml**。

长期：依赖树变更（删 requirements/*.txt、换 PDM）后，记得手动 dismiss 旧 manifest 残留 alert，避免安全面板长期失真。
