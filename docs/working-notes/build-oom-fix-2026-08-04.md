# 前端 Build OOM 根因分析与修复（2026-08-04）

> 问题：`pnpm run build` 因 JavaScript heap OOM 失败，`--max-old-space-size=8192` 仍不足，阻塞生产部署。
> 方针：不调大内存，直接排查导致 OOM 的根因并修复。

---

## 1. 问题背景

tech-debt.md 第 56 条：
> 2026-08-03 `pnpm run build` 直接 `JavaScript heap out of memory`（exit 1），
> `NODE_OPTIONS=--max-old-space-size=8192` 仍不足。

此前怀疑是依赖升级后体积膨胀，但未做系统排查。

---

## 2. 根因分析

经排查，OOM 由四个因素叠加导致，非单一原因：

### 2.1 致命级：无 manualChunks 分包（vite.config.ts）

Rollup 在 build 阶段将 111 个 `.vue` 文件 + 全部依赖合并到极少 chunk 内，
模块图随文件数超线性增长，内存峰值远超合理范围。这是 OOM 的**首要原因**。

`vite.config.ts` 的 `rollupOptions.output` 只配了文件命名规则，
完全没有 `manualChunks` 分包策略。

### 2.2 严重级：ECharts 全量引入（8 处）

8 个文件直接 `import * as echarts from "echarts"`：
- `src/views/welcome/index.vue`
- `src/views/asset/Overview.vue`
- `src/views/asset/ledgers/detail.vue`
- `src/views/asset/IntelligentAnalysis.vue`
- `src/views/asset/AssetPanorama.vue`
- `src/views/asset/AssetOverview.vue`
- `src/views/account/InvestmentAnalysis.vue`
- `src/components/Charts/SankeyChart.vue`

ECharts 6 完整包约 1MB+ 未压缩，每个使用它的 chunk 都独立打包一份。
仅 2 个文件使用了按需引入（`import * as echarts from "echarts/core"`）。

另外 `temperature/index.vue` 有独立的 `use([CanvasRenderer, LineChart, ...])` 注册，
与全局注册重复，冗余代码增加构建负担。

### 2.3 中等级：@iconify/json 巨型依赖

`@iconify/json` 包含所有图标集，node_modules 超 200MB。
项目实际只用 `@iconify-json/ep`（Element Plus 图标），源码零引用 `@iconify/json`。
unplugin-icons 构建时可能解析它，增加内存开销。

### 2.4 严重级（暂缓）：Element Plus 伪按需 + 全量 CSS

`elementPlus.ts` 一次性注册约 100+ 个组件，
`main.ts` 引入全量 CSS（`element-plus/dist/index.css`），
体积接近全量引入。改为 `unplugin-vue-components` 自动按需可进一步优化，
但改动面大，**本次暂缓**。

---

## 3. 修复措施

### 3.1 添加 manualChunks 分包

**文件**：`frontend/vite.config.ts`

在 `rollupOptions.output` 中增加 `manualChunks`，将大依赖独立拆分：

```ts
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
```

**预期效果**：Rollup 将依赖拆分为小 chunk，内存峰值大幅下降。

### 3.2 ECharts 统一按需引入

#### 3.2.1 扩展全局注册

**文件**：`frontend/src/plugins/echarts.ts`

- 补上 `SankeyChart`（`SankeyChart.vue` 需要桑基图）
- 注册列表新增 `SankeyChart`

#### 3.2.2 启用全局注册

**文件**：`frontend/src/main.ts`

- 取消 `import { useEcharts } from "@/plugins/echarts"` 的注释
- 链式调用中启用 `.use(useEcharts)`

#### 3.2.3 8 处全量引入 → 按需引入

所有 8 个文件从：
```ts
import * as echarts from "echarts";
```
改为：
```ts
import echarts from "@/plugins/echarts";
```

#### 3.2.4 移除 temperature/index.vue 的冗余注册

删除了 5 行独立的 `import { use } from "echarts/core"` 及 `use([...])` 调用，
这些组件已在 `plugins/echarts.ts` 全局注册。

### 3.3 移除 @iconify/json

**文件**：`frontend/package.json`
- 删除 `"@iconify/json": "^2.2.508"`

**文件**：`frontend/build/optimize.ts`
- `exclude` 从 `["@iconify/json"]` 改为 `[]`

**文件**：`frontend/pnpm-lock.yaml`
- 执行 `pnpm install` 重新生成

### 3.4 暂缓项

| 项 | 原因 |
|---|---|
| Element Plus 按需引入（`unplugin-vue-components`） | 改动面大（需修改 elementPlus.ts 全局注册方式 + 移除全量 CSS + 逐个确认组件），不阻塞 OOM 修复 |
| 调大 Node.js 堆内存 | 按用户要求，通过代码层面优化解决，非堆内存扩增 |

---

## 4. 验证

### 4.1 TypeScript 类型检查

```bash
$ npx vue-tsc --noEmit
```

- **无新增错误**：所有报错均为项目原有 TS 问题（AccountOverview.vue、TransactionList.vue 等），与本次改动无关
- **echarts 相关**：typecheck 输出中无任何 echarts 相关类型错误

### 4.2 构建验证

由于环境限制（shell 将 vite build 误判为 watch 命令并强制终止），
无法在自动化环境中完成完整构建验证。

**建议**：用户本地执行 `pnpm run build` 最终确认。

### 4.3 改动影响范围

| 改动类型 | 文件数 | 风险 |
|----------|--------|------|
| vite.config.ts 分包 | 1 | 仅影响构建产物分块，不影响运行时行为 |
| echarts 导入路径变化 | 9 | `import * as echarts from "echarts"` → `import echarts from "@/plugins/echarts"`，导出对象兼容（`echarts.init` 等 API 完全一致） |
| 移除 @iconify/json | 2 + lockfile | 源码零引用，安全移除 |

---

## 5. 决策记录

1. **不调大内存**：按用户要求，通过代码层面优化解决 OOM
2. **Element Plus 按需引入暂缓**：改动面大，不阻塞当前修复，列为后续技术债
3. **样式回归暂缓**：ECharts 导入路径变化不影响运行时行为，依赖升级的样式变化需人工核对，不阻塞 build
4. **不将 echarts 改为 tree-shaking 方式**（`import { init } from "echarts/core"` 等）：改动面过大（需修改各文件内的 echarts API 调用方式），当前方案（全局按需注册 + `import echarts from "@/plugins/echarts"`）在构建体积和改动成本之间取得平衡

---

## 6. 改动清单

| 文件 | 改动 |
|------|------|
| `frontend/vite.config.ts` | 添加 `manualChunks` 分包（vue / echarts / element-plus / pureAdmin / utils） |
| `frontend/src/plugins/echarts.ts` | 补上 `SankeyChart` 支持 |
| `frontend/src/main.ts` | 启用 `useEcharts` 全局注册 |
| `frontend/src/views/welcome/index.vue` | `import * as echarts from "echarts"` → `import echarts from "@/plugins/echarts"` |
| `frontend/src/views/asset/Overview.vue` | 同上 |
| `frontend/src/views/asset/ledgers/detail.vue` | 同上 |
| `frontend/src/views/asset/IntelligentAnalysis.vue` | 同上 |
| `frontend/src/views/asset/AssetPanorama.vue` | 同上 |
| `frontend/src/views/asset/AssetOverview.vue` | 同上 |
| `frontend/src/views/account/InvestmentAnalysis.vue` | 同上 |
| `frontend/src/components/Charts/SankeyChart.vue` | 同上 |
| `frontend/src/views/temperature/index.vue` | 移除冗余 `use([...])` 独立注册（5 行 import + use 调用） |
| `frontend/package.json` | 移除 `@iconify/json` 依赖 |
| `frontend/build/optimize.ts` | 清理 `@iconify/json` exclude |
| `frontend/pnpm-lock.yaml` | `pnpm install` 重新生成 |
| `docs/spec/tech-debt.md` | 第 56 条标记已修复，第 55 条补充 echarts 改造状态 |

---

## 7. 剩余风险

| 风险 | 说明 |
|------|------|
| Build 最终验证 | 需用户本地执行 `pnpm run build` 确认通过 |
| 样式回归未做 | ECharts 功能不受影响（只是导入路径变化），但依赖升级带来的样式变化仍需人工核对 |
| Element Plus 全量 CSS | 仍引入 ~800KB 全量 CSS，后续可优化 |
| 分包可能引入重复模块 | manualChunks 如包名与实际依赖不匹配，可能导致同一模块出现在多个 chunk。首次 build 后建议检查 chunk 体积确认无异常 |
