# CNB `dev` 领先 GitHub 的提交清单与救援口径（2026-10-11）

> 关联：`cnb-github-mirror-route-2026-10-11.md`（路线决策）、CNB #125 / GitHub #2032、#2034
> 用途：管道 A（GitHub → CNB 快进镜像）**已停摆**，本文件把「CNB 侧独有提交」逐条核到它对应
> 哪张 GitHub 卡、哪一步该回流，免得救援时把工作量估大或漏掉。

## 1. 为什么这份清单要单独立档

路线决策文件（`cnb-github-mirror-route-2026-10-11.md`）给出的是**口径**：单源 + 两条单向管道。
但接手的人第一句话一定是「那 CNB 侧到底多出哪些东西、要不要全部搬回来」。答不上这个，
救援就会在「全搬」和「不管」之间摇摆。

本轮实测的读数是 CNB `dev` 相对 GitHub `dev` 有 **6 个独有提交**。逐一核完的结论是：
**其中 1 个（`fix/2034-category-dedup`）需要重新提交到 GitHub，其余多是镜像产物、不必动。**

## 2. 清单（`gh/dev 16e807c4` → `cnb/dev 82cbf694`，全量 fetch 读数）

| # | 提交 | 主题 | 该不该回流 |
|---|---|---|---|
| 1 | `dc3feb28` | welcome 移除资产构成环形图（#2034 一轮） | 内容是**重复的**，见 §3.1 |
| 2 | `49272b6a` | 同上（原始提交，被 `dc3feb28` 合并带过来） | 同上 |
| 3 | `510c787f` / `17e8e6be` | issue 镜像脚本 + `.cnb.yml`（#2） | 走「把 CNB 造的资产正规化」独立一步 |
| 4 | `c5219ef7` / `b0485fe7` | welcome 三项指标走直出字段（#119 修法 A） | 同上（含单测，需 PR 入库） |
| 5 | `644a9aa7` / `e6d2ad37` | **`fix/2034-category-dedup`（CNB PR #125）** | ✅ **需要回流**，理由见 §3 |

## 3. CNB PR #125 是本清单里唯一「内容独有且已合入」的一项

### 3.1 它的一半内容是重复的

`dc3feb28`（以及被它合并的 `49272b6a`）做的事——welcome 去掉资产构成环形图、右半边改放净资产 —
**GitHub 侧已经在 `dev` 里了**。判定依据不是标题像，而是内容：

```bash
# GitHub dev 上的同名工作记录已经记下了这两个动作
curl -s https://raw.githubusercontent.com/imoyao/fundmate/dev/\
docs/working-notes/page-split-welcome-vs-panorama-2026-08-13.md | \
  grep -n "删除随图失效的 distributionLogic\|welcome 不再请求"
```

同时 `frontend/src/views/welcome/composables/distributionLogic.ts` 在 GitHub `dev` 上**已不存在**。
⇒ 这部分**不必重做**。

### 3.2 但另一半不是重复的，而且**没有任何替代品**

`e6d2ad37`（CNB PR #125 的第二个提交）做的是 **panorama 首屏「资产透视」区块的收尾**：

- 删除 `<AssetInsightPanel class="mb-4" />` 挂载与组件本体；
- 瀑布卡片标题「资产大类构成」→「资产大类」，口径 tooltip 去掉「按资产大类拆解」这种像控件的措辞；
- 新增 `scripts/tests/welcome_structure_dedup.test.js`（11 条，含「区块不得回潮」与
  「`category_distribution` 消费方白名单」）。

**这些改动在 GitHub 侧一个都不存在**：`dev` 上 `AssetInsightPanel.vue` 还在，
`panorama/index.vue` 还挂着它，`scripts/tests/welcome_structure_dedup.test.js` 返回 404。
也就是说，GitHub 上的 #2032（标题与字段对不上）**原样成立**。

### 3.3 一个必须说清的坑：CNB 的 `git show` 会给出**假的合并结果**

`644a9aa7`（`git ls-tree` 显示该目录已消失）与 `7e227b84`（显示文件还在）**同名父目录的
写入顺序相反**，而 `7e227b84` 晚于合并提交。按纯拓扑求值是**不可判定**的。

要判断文件真实去向，只能读**对象**、不能读 `git ls-tree` 的派生结果：

```bash
git cat-file -p <提交>^{tree}              # 逐层取 tree 对象
git cat-file -p <frontend/src tree 的 sha> # 再往下取一层
```

本轮的读数（全部走了对象读取）：`main` / `dev` 两侧**都**没有 `frontend/src/components/AssetInsight/`。
⇒ 结论：**CNB `dev` 里「资产透视」已删、GitHub `dev` 里还在**，两侧对同一张卡给出了相反的答案。

> 这也解释了为什么本仓 `dev` 上 `AssetInsightPanel.vue` 一直没消失：**不是谁改回来了，
> 而是删除动作从来没到过 GitHub。**

## 4. 救援口径（建议）

1. **不要整支 cherry-pick `644a9aa7`**：它含重复内容，cherry-pick 会制造与 GitHub `dev` 的冲突；
2. #119 / 镜像脚本 / `.cnb.yml` 走路线决策里的「第 1 步：把 CNB 造的资产正规化」；
3. **#2034 的收尾按它自己的卡重新落一次 PR**（即在 GitHub 上真的把「资产透视」区块处理掉），
   而不是把 CNB 的提交搬过来——搬到 GitHub 后仍要过 GitHub 的评审与门禁，
   不如直接按卡做，顺便把 `welcome_structure_dedup.test.js` 一并入库；
4. 在 CNB 的镜像卡（如 #104）评论区把「本卡在 CNB 侧已修、GitHub 侧未修」**明确写出来**，
   避免下次有人看到 CNB 的代码以为已经修好了。

## 5. 一句话

**CNB 侧领先的不是「新功能」，而是「同一张卡的另一种最终状态」。**
对 #2032 / #2034 而言，两侧不是一个人先做了、另一个还没做，而是**两个仓对同一张卡各自走到了不同的终点**。
所以救援的形态是「在 GitHub 上把这张卡重新做对」，不是「把 CNB 的提交搬过来」。
