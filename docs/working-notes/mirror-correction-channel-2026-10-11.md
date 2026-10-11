# CNB 镜像卡的更正通道（#120 方案 A + B）

> 结论先行：镜像链路缺的**不是同步能力，而是「更正」这个动作**。本备忘记录 #120 的落地方式、
> 为什么不做方案 C、以及一次真实演练的留痕。
> 相关：`scripts/bridge/github_cnb_issues.py`、`scripts/bridge/mirror_correction.py`、
> `AGENTS.md`「失实信息修正纪律」。

## 一、问题回顾

`github_cnb_issues.py` 的取舍是「**只增不覆盖**」——CNB 侧人工调过的正文不会被覆盖，理由正当。
代价是另一件事：**GitHub 侧后来的更正永远传不过来**，镜像卡永久停在建卡那一刻。

本仓对原卡已有纪律：正文失实**用评论追加更正，禁止覆盖正文**。这条纪律在 GitHub 上能执行，
在镜像卡上**执行不了**——镜像卡是只读的，下一个人不知道要去 GitHub 看，而更正写在 GitHub、
CNB 侧（镜像卡真正被读到的地方）看不到。

活证据是镜像卡 #106（= GitHub imoyao/fundmate#2034）：正文引用 `WelcomeAssetBoard.vue:119-130`，
该行早随 #980 拆页删除；溯源块里的「评论数：0」「状态：open」也都是建卡快照。

## 二、方案 A：溯源块加「时效声明」（已做）

改 `build_body`，在溯源块里补三样东西：

1. `镜像生成时间：<UTC>` —— 之前只有 GitHub 的**创建**时间，读者容易误以为「本卡很新」；
2. 「本卡是**建卡时快照**（截至 X）、不覆盖后续变更、正文行号可能与当前代码不一致」+
   「正文若与 GitHub 不符，**一律以 GitHub 为准**」——把「看起来权威的过期事实」降级为
   「明确的过期快照」；
3. 一段 `📝 **更正**：…` —— 写明更正写在**本卡评论区**、格式是什么、命令入口在哪。

判据落在 `scripts/tests/test_bridge_mirror.py`，**只截溯源块**（`\n---\n` 之前）断言，不整篇搜
关键词：原文正文自己也可能提到「更正」，整篇搜会假绿。

## 三、方案 B：评论区更正台账（已做）

新增 `scripts/bridge/mirror_correction.py`，把「在镜像卡评论区写更正」从一句纪律变成一条命令：

```bash
python scripts/bridge/mirror_correction.py list --cnb 106
python scripts/bridge/mirror_correction.py add --cnb 106 --date 2026-10-11 \
    --correction '❌ 正文「x」→ ✅ 实际「y」（依据：PR #115）'            # dry-run
python scripts/bridge/mirror_correction.py add ... --apply              # 真正发布
```

设计要点：

- **单向、只增**：只往 CNB 写评论，绝不回写 GitHub；不碰镜像卡正文、标签与状态。
- **幂等**：幂等键 = `sha1(卡片编号 + 日期 + 逐条摘要)` 前 12 位，写在评论末尾的 HTML 注释里
  （读者看不见、脚本看得见）。重复执行跳过，返工用 `--force`。
- **防误用**：写入前确认目标卡带 `GitHub 同步` 标签或正文含 `GitHub 编号：#N`，否则拒绝——
  写到人工卡上比漏写更贵。
- **零新依赖**：复用 `github_cnb_issues.py` 的 `cnb_api`（标准库 urllib）。

### 为什么不把评论同步进正文（方案 C，不做）

方案 C 要「正文 = 快照 + 更正日志」，代价是增量去重 + 幂等键 + 每次运行改写正文——
恰好把「只增不覆盖」这条取舍从根上推翻，也就是把 #120 想保护的东西扔掉。评论台账用
**零正文改动**拿到同样的可读性：正文说「去哪里找更正」，评论承载更正本身。

## 四、真实演练（#120 验收第 4 条）

对镜像卡 #106 执行了方案 B 的首次更正，两条：

1. `WelcomeAssetBoard.vue:119-130` / 「按资产大类」那行 → 已随 #980 拆页删除；
2. 「环形图消费 `market_distribution`」→ 实为 `distributions.category_distribution`，
   与瀑布图同字段同口径（依据 PR #115）。

记录：更正键 `410f1bcc4da1`；随后**原样重复执行一次**，输出
`⏭️ 这条更正已发布过（更正键 …），跳过。`——幂等有效性在真实接口上验证过，不只是单测里。

## 五、守卫接线

`scripts_test` job（`.github/workflows/ci.yml`）原本只跑 `node --test "scripts/tests/*.test.js"`，
**覆盖不到 `scripts/bridge/` 的 Python 脚本**。本卡一并补上
`python -m unittest discover -s scripts/tests -p "test_*.py"`，把两个脚本的纯函数与 `add` 路径
（网络全打桩）钉住。

## 六、边界（本卡不管什么）

- **不管评论同步**：GitHub 原卡的新评论不会自动回填到镜像卡。那是 #117 的硬要求 ②，
  本卡只保证「有人发现失实时有地方写、且写得成」。
- **不管状态同步**：GitHub 关了 CNB 不自动关（沿用既有取舍）。
- **不追溯存量**：已建的镜像卡正文仍是旧文案。方案 A 只作用于**之后新建**的卡——
  这是「只增不覆盖」的直接推论，需要改写存量则得先与 #117 的取舍对齐。
