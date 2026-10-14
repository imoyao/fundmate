#!/usr/bin/env python3
"""守门：git-sync 凭据引用必须挂在**插件任务级**，且用 `imports`（源 CNB #148）。

WHY：2026-10-12 两条形态都实测踩过，报错完全不同，把人带向了两个错方向：

  ① 凭据挂在**流水线级** `imports`（`push:` 下一层、`stages:` 之上一行）⇒ 死在 Prepare：
         vars.yml declares allow_images and can only be referenced by plugin tasks.
     因为 vars.yml 必须声明 `allow_images: [tencentcom/git-sync]`（否则插件读不到密钥），
     而流水线级引用**不算「插件任务」**，平台判定「声明了 allow_images 却没在插件任务里用」
     → 直接拒绝，连 stage 都进不去。

  ② 改挂**插件任务级 `settingsFrom`** ⇒ Prepare 过了、进得了 stage，但推不上去：
         fatal: could not read Username for 'https://github.com'
     `settingsFrom` 的语义是「从文件**加载插件参数**」（KEY 直接当插件参数名），
     **不注入环境变量**；而 `settings` 里的 `${GIT_USERNAME}` 是环境变量替换，此时无从解析
     ⇒ 插件拿到空的 username/password ⇒ `setup_https()` 跳过写 `~/.git-credentials`
     ⇒ git 交互式要用户名而失败。

✅ 正确形态：**插件任务级 `imports`**（与 `image` 平级）。依据 CNB 文档
   《文件引用 › image 检查说明》：镜像任务参数「可通过 `settingsFrom` 设置，也可通过
   `imports` 引入后以**环境变量**方式设置，**两种方式均视为插件任务引用文件**」。
   即：插件任务级 `imports` 同样是合规的插件引用（`allow_images` 检查通过），
   且它**注入环境变量**，`settings` 里的 `${GIT_USERNAME}` 才解析得出。
   这也是 git-sync 插件作者给的官方示例形状（其 example.yml 即此法）。

  口诀：**「引用挂在哪」决定合规（必须插件任务内）；
        「用 imports 还是 settingsFrom」决定 `${VAR}` 能不能解析（要解析就用 imports）。**

判据（三条，都只看静态结构，不拉网络）
--------------------------------------
1. **密钥类 URL 出现在流水线级（非插件任务级）引用里** ⇒ 报错（原文 ① 形态）。
   「插件任务级」= 与 `image` 同级的对象内部的 `imports` / `settingsFrom`；
   其余位置（`push:` / `crontab:` 元素对象、`stages:` 之上）都算流水线级。
2. **插件任务用 `settingsFrom` 引用密钥文件，且 `settings` 里对其凭据用了 `${...}`** ⇒ 报错
   （原文 ② 形态）。`settingsFrom` 不注入环境变量，`${VAR}` 解析不出；要用 `${VAR}` 就得 `imports`。
3. **同一份 URL 同时出现在 `imports` 与 `settingsFrom`** ⇒ 报错。
   平台不允许同一引用对象两种语义并存，且这是过渡期最容易留下的半吊子改动。

不做什么
--------
**不拉网络、不校验 URL 可达性**：`fundmate-secret` 对 API / token 一律 403
（`Secret repos do not support token access`），守卫读不到也不该读。
判据 1 只读**仓库内** `.cnb.yml`；判据 2 只看「settingsFrom 引密钥 + settings 用 ${}」这一组合，
不依赖任何外部文件。

用法
----
    python scripts/guard_secret_imports.py            # 检查仓库根 .cnb.yml
    python scripts/guard_secret_imports.py --file x   # 检查指定文件
退出码 0 = 通过，1 = 发现问题。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# 密钥仓库 `vars.yml` 在本仓的**内容同步模板**（见 docs/ops/git-sync-secret-vars.example.yml 文件头：
# 「真正被读取的是密钥仓库里的 vars.yml……故模板落在代码仓里」）。
SECRET_TEMPLATE = Path('docs/ops/git-sync-secret-vars.example.yml')

# 插件任务标记：与 `image` 同级、可用来引用外部文件的键名，按 CNB 语法只有两种。
PLUGIN_TASK_KEYS = ('imports', 'settingsFrom')

# `settings` 里常被用来引用凭据的环境变量名（命中即认为该键需要 `${}` 解析）。
CREDENTIAL_KEYS = ('username', 'password', 'ssh_key')


def _is_secret_url(value: str) -> bool:
    """判断一个引用 URL 是不是「密钥类文件」。

    **有意不要求 URL 里含 `secret`**（2026-10-14 修，源 CNB #179）：
    密钥仓库没必要叫 `*-secret`，改个名字（如 `duoduobei/fundmate-vars`）就会让
    判据 1 静默失效——**而它是安全判据，静默放过比误报贵得多**。
    改为同时认两种形态：① URL 里含 `secret`；② 文件名形如 `<名>.vars.yml`
    （本仓的约定是密钥文件叫 `vars.yml`，`fundmate-secret` 只是**当前位置**的名字，
    不是判据的唯一入口）。
    """
    low = value.lower().strip()
    if 'secret' in low:
        return True
    tail = low.rstrip('/').rsplit('/', 1)[-1].split('?')[0]
    # `vars.yml` / `xxx.vars.yml` / `xxx-vars.yml` 都认；`vars.example.yml` 不认（那是文档）。
    return tail == 'vars.yml' or (tail.endswith('.vars.yml') and not tail.endswith('.example.vars.yml'))


def _vals(v) -> list[str]:
    items = v if isinstance(v, list) else [v]
    return [x.strip() for x in items if isinstance(x, str)]


def _iter_branch_events(data: dict):
    """产出「分支段 → 事件 → job 列表」三层，只跳过锚点键（`.` 开头）。

    ⚠️ **`$` 段必须扫，不能跳过**（2026-10-14 修，源 CNB #269）：
    初版把 `$` 和锚点键一起 `continue` 掉了，于是判据 1 / 判据 2 **恰好漏掉真 bug 所在的段** ——
    `$` 段 push 下的 `认领同步`（`tencentcom/http-request` 插件）把 `imports` 挂在 **job 对象**上
    （= 流水线级），每跑必红、死在 Prepare：
        vars.yml declares allow_images and can only be referenced by plugin tasks.
    更坏的是**守卫当时报绿**（回退探针实测 MISSED）：它把「刚修好的 bug」误报成「本来就合规」，
    假绿比假红贵得多。`$` 只是「所有分支」的写法，仍是一个分支段，插件任务规则完全适用。
    """
    for branch, events in (data or {}).items():
        if branch.startswith('.'):
            continue
        if not isinstance(events, dict):
            continue
        for event, jobs in events.items():
            yield branch, event, jobs if isinstance(jobs, list) else []


def _iter_plugin_stages(data: dict):
    """产出所有 `stages` 元素（stage dict），**只要它带了引用键或 `script`**。

    ⚠️ 早先这里写的是「产出含 `image` 的 stage」——那个过滤条件**把真实形态漏掉了**
    （2026-10-14 回退探针实测 MISSED）：`认领同步` 的 `image` 来自 **job 级 `docker.image`**
    （经 YAML 锚点 `&claim-job` 注入），stage 自身**没有** `image` 键
    ⇒ 它压根不在遍历结果里 ⇒ 判据 4 看不见它。

    ⚠️ 这正是本仓反复栽的同一类错：**判据的遍历范围本身就是判据的一部分**，
    过滤条件写窄了的表现是**静默通过**（#269 第一轮、#171 都栽在这）。

    新语义：stage 只要带 `script` / `commands` / `imports` / `settingsFrom` / `settings`
    任一，就纳入遍历——判据各自在里面再挑它关心的。**宁多扫，不要漏。**
    """
    interesting = ('script', 'commands', 'imports', 'settingsFrom', 'settings')
    for branch, event, jobs in _iter_branch_events(data):
        for job in jobs:
            if not isinstance(job, dict):
                continue
            for stage in job.get('stages') or []:
                if not isinstance(stage, dict):
                    continue
                if any(k in stage for k in interesting):
                    yield branch, event, stage


def _is_script_task(stage: dict) -> bool:
    """带 `script` / `commands` ⇒ **脚本任务**（`image` 只是执行环境，不作为插件任务）。

    依据 CNB《文件引用 › 权限检查 › image 检查说明》原文：
      「**Job 同时设置 `image` 和 `script` 属于以 image 作为执行环境的脚本任务**」
      「非插件任务的 image 为空字符串，无法匹配任何 glob 表达式；配置文件声明了
        `allow_images` 将不能被非插件任务引用」。

    即：脚本任务上的 `image` 只是**运行环境**（跑 `script` 的容器），它是插件镜像这件事
    并不成立 ⇒ 引用一份声明了 `allow_images` 的密钥文件**必然被拒**，
    且报错与「挂在第几层」无关（源 CNB #269：改了两轮都还是同一条）。

    ⚠️ **`image` 不必在 stage 自己身上**（源 CNB #269 第二轮，2026-10-14）：
    CNB 的构建环境可由 **job 级 `docker.image`** 或 pipeline 级提供，
    `认领同步` 就是靠 YAML 锚点 `<<: *claim-job` 把 `docker.image` 注进来的 ——
    stage 自身没有 `image` 键。故判据只看 **`script` / `commands` 是否存在**：
    「有没有 shell 命令」才是「是不是脚本任务」的判据，「image 从哪儿来」不是。
    """
    return bool(stage.get('script')) or bool(stage.get('commands'))


def _is_gitsync_vars_url(value: str) -> bool:
    """判断引用 URL 是不是 **git-sync 的那份 `vars.yml`**（= 声明了 `allow_images` 的密钥文件）。

    ⚠️ 判据 4 的关键前提（CNB #269 第二轮的修正）：
    「脚本任务不能用密钥引用」是**过宽**的说法。真正被 CNB 拒的是一条**更窄**的规则——

    > 非插件任务的 image 为空字符串，无法匹配任何 glob 表达式；
    > 配置文件**声明了 `allow_images`** 将不能被非插件任务引用。

    即：**拒的是「文件里有 `allow_images`」，不是「脚本任务引用」。** 一份只声明
    `allow_slugs` 的密钥文件，被脚本任务 `imports` 引是**合法**的（CNB 官方示例
    「流水线密钥文件引用」就是这么写的：普通脚本任务 `script: docker login -u ${DOCKER_USER}`
    + `imports: .../secret.yml`，该文件只声明 allow_slugs / allow_events / allow_branches）。

    而 `allow_images` 是 git-sync 那条链的**必需品**（插件任务不声明它读不到密钥），
    本仓的约定是它写在 `vars.yml` 里。守卫读不到密钥仓库（403），故按**文件名约定**判：
    形如 `vars.yml` / `*.vars.yml` 的即视为「带 allow_images 的 git-sync 文件」。
    `claim-sync-env.yml` 之类不长这样 ⇒ 放行。

    ⚠️ 名字约定与 `SECRET_TEMPLATE`（docs/ops/git-sync-secret-vars.example.yml 里
    `allow_images` 的存在）互为印证：模板里有 `allow_images`，文件名是 `vars.yml`。
    """
    low = value.lower().strip()
    tail = low.rstrip('/').rsplit('/', 1)[-1].split('?')[0]
    return tail == 'vars.yml' or (tail.endswith('.vars.yml') and not tail.endswith('.example.vars.yml'))


def check_secret_ref_on_script_task(data: dict) -> list[str]:
    """判据 4：**脚本任务**上不得引用「声明了 `allow_images` 的」密钥文件，也不得用 `settingsFrom`。

    ⚠️ 这条判据**收窄过一次**（2026-10-14，CNB #269 第二轮），别当成「脚本任务一律不能引密钥」：

    | 形态 | 判 |
    |---|---|
    | 脚本任务 + `imports` 引**带 `allow_images`** 的文件（`vars.yml`） | ❌ 必死在 Prepare（#269 真实形态） |
    | 脚本任务 + `settingsFrom` 引密钥 | ❌ `settingsFrom` 是「加载插件参数」语义，脚本任务没有插件参数 |
    | 脚本任务 + `imports` 引**不带 `allow_images`** 的文件（`claim-sync-env.yml`） | ✅ 合法（CNB 官方示例形态） |
    | 插件任务（`image` + `settings`，无 `script`） | ✅ 由判据 1/2/3 管，本条不管 |

    前三条判据判的是「挂在第几层」（**语法**），本条判的是「挂它的那个 job 是不是插件任务，
    以及被引文件是不是给插件用的」（**语义**）——#269 的真根因在这层，前三轮都抓不到。
    """
    problems: list[str] = []
    for branch, event, stage in _iter_plugin_stages(data):
        if not _is_script_task(stage):
            continue
        where = f'{branch}.{event} 的 `{stage.get("name") or "（无名 stage）"}`'
        script_hint = '它带 `script` ⇒ 是**脚本任务**（`image` 只是运行环境，来源不限 stage 自身）'

        # (a) `settingsFrom`：脚本任务上永远没有「插件参数」可加载。
        for url in _vals(stage.get('settingsFrom')):
            if not _is_secret_url(url):
                continue
            problems.append(
                f'{where} {script_hint}，却用 `settingsFrom` 引密钥文件 `{url}`。'
                '`settingsFrom` 的语义是「从文件加载**插件参数**」，脚本任务没有插件参数可加载。'
                '改用 `imports`（注入环境变量），或把它改造成真正的插件任务。'
            )

        # (b) `imports` 引「带 allow_images 的文件」：CNB 明确拒绝。
        for url in _vals(stage.get('imports')):
            if not _is_secret_url(url) or not _is_gitsync_vars_url(url):
                continue
            problems.append(
                f'{where} {script_hint}，却用 `imports` 引了 git-sync 的密钥文件 `{url}`'
                '（该文件声明了 `allow_images`）。CNB《文件引用 › image 检查说明》：'
                '「配置文件声明了 allow_images 将不能被非插件任务引用」'
                '⇒ 该作业**必然死在 Prepare**：'
                'declares allow_images and can only be referenced by plugin tasks。'
                '（#269 实测：改挂载层级治不了它，真根因在文件里的 allow_images。）'
                '正确做法是另起一份**不声明 allow_images** 的密钥文件'
                '（如 `claim-sync-env.yml`，模板 docs/ops/claim-sync-secret-env.example.yml），'
                '脚本任务 `imports` 引那一份。'
            )
    return problems


def check_pipeline_level_secret_refs(data: dict) -> list[str]:
    """判据 1 + 3：密钥类 URL 必须挂在插件任务级，且不得两种语义并存。"""

    problems: list[str] = []
    # 判据 3 用它判「同一引用对象两种语义并存」——按 **URL** 维度就够（同一份密钥文件）。
    plugin_level: set[str] = set()
    for _branch, _event, stage in _iter_plugin_stages(data):
        for key in PLUGIN_TASK_KEYS:
            plugin_level.update(_vals(stage.get(key)))

    problems += _check_pipeline_level(data, plugin_level)
    problems += _check_dual_use(data)
    return problems


def _iter_pipeline_level_refs(data: dict):
    """产出流水线级（非插件任务级）的 imports/settingsFrom 引用。

    做法：从**事件下的 job 对象直接**取这两个键 —— 插件任务级的引用在 `stages[*]` 里，
    这一层扫不到，正是判据要的「挂错了位置」那一层。
    """
    for branch, event, jobs in _iter_branch_events(data):
        for i, job in enumerate(jobs):
            if not isinstance(job, dict):
                continue
            for key in PLUGIN_TASK_KEYS:
                if key in job:
                    for url in _vals(job[key]):
                        yield key, url, f'{branch}.{event}[{i}].{key}'


def _check_pipeline_level(data: dict, plugin_level: set[str]) -> list[str]:
    """判据 1：**任何** job 对象上的密钥类引用都算挂错位置（不论别处挂得多对）。

    ⚠️ 曾经这里写的是「URL 只要在**任意**插件任务级出现过就放过」（`if url in plugin_level: continue`），
    理由是「同 URL 在别处合规就不算两种语义并存」。**那条白名单把判据 1 整个架空了**：
    本仓所有 job 引的是**同一份** `vars.yml` ⇒ 只要 git-sync 的某条 stage 挂对了，
    **任何一条挂错的 job 都会被放过**（2026-10-14 回退探针实测 MISSED，两次都是这个原因）。

    正确语义是**逐挂载点**判：合规与不合规是**每个引用位置各自**的属性。
    URL 级别的去重只服务于「别把同一处报两遍」，不能拿来当豁免。
    """
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for key, url, trail in _iter_pipeline_level_refs(data):
        if not _is_secret_url(url):
            continue
        if (key, url, trail) in seen:
            continue
        seen.add((key, url, trail))
        problems.append(
            f'{url} 被**流水线级** `{trail}` 引用。密钥文件声明了 allow_images，'
            '只有**插件任务级**引用才合规（流水线级会让整条作业死在 Prepare：'
            'declares allow_images and can only be referenced by plugin tasks）。'
            f'请把它移到插件任务内部（与 `image` 同级）并改用 `imports`。'
        )
    return problems


def _check_dual_use(data: dict) -> list[str]:
    imports: dict[str, str] = {}
    settings_from: dict[str, str] = {}
    for branch, event, stage in _iter_plugin_stages(data):
        for key in PLUGIN_TASK_KEYS:
            for url in _vals(stage.get(key)):
                bucket = imports if key == 'imports' else settings_from
                bucket.setdefault(url, f'{branch}.{event}.stages')
    problems: list[str] = []
    for url, trail in sorted(imports.items()):
        if url in settings_from:
            problems.append(
                f'{url} 同时被插件任务的 imports（{trail}）与 settingsFrom（{settings_from[url]}）引用。'
                '同一份密钥文件两种语义并存：`imports` 注入环境变量、`settingsFrom` 只加载插件参数，'
                '留着两份只会让下一轮继续踩坑；迁移时必须删掉旧的那一种。'
            )
    return problems


def check_settingsfrom_var_substitution(data: dict) -> list[str]:
    """判据 2：插件任务用 `settingsFrom` 引密钥，却在 `settings` 里用 `${VAR}` 引凭据。

    `settingsFrom` 从文件**加载插件参数**，不注入环境变量 ⇒ `${VAR}` 无从解析
    （实现在环境变量里只有 `PLUGIN_*`），插件拿到的 username/password 为空，
    表现为 `fatal: could not read Username for 'https://github.com'`（#148 ② 原文）。
    """
    problems: list[str] = []
    for branch, event, stage in _iter_plugin_stages(data):
        refs = _vals(stage.get('settingsFrom'))
        if not any(_is_secret_url(u) for u in refs):
            continue
        settings = stage.get('settings') or {}
        if not isinstance(settings, dict):
            continue
        touched = [
            k
            for k in CREDENTIAL_KEYS
            if isinstance(settings.get(k), str) and '${' in settings[k]
        ]
        if touched:
            problems.append(
                f'{branch}.{event} 的插件任务用 `settingsFrom` 引密钥文件，'
                f'却把 {touched} 写成 `${{VAR}}` 环境变量替换。`settingsFrom` 只加载插件参数、'
                '**不注入环境变量**，`${VAR}` 解析不出 ⇒ 插件拿到空凭据 ⇒ git 报 '
                "`could not read Username for 'https://github.com'`。"
                '改用插件任务级 `imports`（它注入环境变量，`${VAR}` 才解析得出）。'
            )
    return problems


def _secret_template_has_allow_images(path: Path) -> bool:
    template = path.resolve().parent / SECRET_TEMPLATE
    if not template.exists():
        return False
    try:
        content = yaml.safe_load(template.read_text(encoding='utf-8'))
    except yaml.YAMLError:
        return False
    return isinstance(content, dict) and bool(content.get('allow_images'))


def self_check() -> list[str]:
    """探针（本仓老规矩：守门通过 ≠ 守门有效）。

    用**最小真实形态**验证三条判据都真会报错——判据若被写坏（例如遍历层级算错），
    守卫会全绿通过，而线上照样红。探针在真实数据形态上跑，不依赖线上。
    """
    errors: list[str] = []

    # 合法形态：插件任务级 imports，不该报错。
    ok = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settings': {'username': '${GIT_USERNAME}'},
                        }
                    ]
                }
            ]
        }
    }
    if check_pipeline_level_secret_refs(ok) or check_settingsfrom_var_substitution(ok):
        errors.append('自检探针失败：合法的「插件任务级 imports」形态却被判为不合规。')

    # 合法形态（`$` 段）：`$` 只是「所有分支」的写法，插件任务级 imports 同样该判合规。
    # 这两条既是「别把 `$` 一刀切掉」的正向探针，也是判据 1 的对照。
    ok_dollar = {
        '$': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/http-request',
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                        }
                    ]
                }
            ]
        }
    }
    if check_pipeline_level_secret_refs(ok_dollar) or check_settingsfrom_var_substitution(ok_dollar):
        errors.append('自检探针失败：`$` 段里合法的「插件任务级 imports」被误判为不合规。')

    # ⚠️ 判据 1 的**回归探针**（源 CNB #269，初版实测 MISSED）：
    # `$` 段的 push 里，把 imports 挂在 **job 对象**上（= 流水线级）。
    # 这正是 `认领同步` 的真实形态：每跑必红，而守卫当时报绿。
    bad_dollar = {
        '$': {
            'push': [
                {
                    'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                    'stages': [{'image': 'tencentcom/http-request'}],
                }
            ]
        }
    }
    if not check_pipeline_level_secret_refs(bad_dollar):
        errors.append(
            '自检探针失败：`$` 段的**流水线级** imports 引密钥（#269 的真实形态）没被判据 1 报错'
            ' —— 说明遍历又把 `$` 跳过了。'
        )

    # ⚠️ **判据 4 的探针**（源 CNB #269 的真根因）：脚本任务上挂密钥引用。
    # `image` + `script` 同时存在 ⇒ 它是脚本任务（image 只是运行环境），
    # 前三条判据结构上抓不到它 —— 它们判「挂在第几层」，而这一条判「job 是不是插件任务」。
    bad_script_task = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'name': '认领同步',
                            'image': 'tencentcom/http-request',
                            'script': 'python scripts/bridge/claim_detect.py --apply',
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                        }
                    ]
                }
            ]
        }
    }
    if not check_secret_ref_on_script_task(bad_script_task):
        errors.append(
            '自检探针失败：**脚本任务**（image + script）上用 imports 引密钥文件没被报错'
            ' —— 它会死在 Prepare（非插件任务无法匹配 allow_images，#269）。'
        )
    # 反向：真插件任务（只有 image + settings，无 script）挂了密钥引用**不该**被这条报错
    # （合规与否由判据 1/2/3 管，判据 4 只管「job 类型」）。
    ok_plugin_task = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'name': '同步',
                            'image': 'tencentcom/git-sync',
                            'settings': {'username': '${GIT_USERNAME}'},
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                        }
                    ]
                }
            ]
        }
    }
    if check_secret_ref_on_script_task(ok_plugin_task):
        errors.append('自检探针失败：插件任务（无 script）被判据 4 误报成脚本任务。')

    # ⚠️⚠️ **判据 4 的收窄探针**（源 CNB #269 第二轮）：脚本任务引**不带 `allow_images`**
    # 的密钥文件是**合法**的，不该被报错。
    #
    # 这是「过宽判据」的反向探针：初版判据 4 写成「脚本任务一律不得引密钥」，把 CNB 官方
    # 示例的合法形态（脚本任务 `script: docker login` + `imports: .../secret.yml`，
    # 文件只声明 allow_slugs）一并判红。**判据过宽与过窄一样是 bug**，只是表现形式是
    # 「让人放弃正确做法」。若有人把这条改回一刀切，本探针立刻红。
    ok_script_task_imports = {
        '$': {
            'push': [
                {
                    'stages': [
                        {
                            'name': '认领同步',
                            'image': 'python:3.12-slim',
                            'script': 'python scripts/bridge/claim_detect.py --apply',
                            'imports': [
                                'https://cnb.cool/o/secret/-/blob/main/claim-sync-env.yml'
                            ],
                        }
                    ]
                }
            ]
        }
    }
    if check_secret_ref_on_script_task(ok_script_task_imports):
        errors.append(
            '自检探针失败：脚本任务 `imports` 引**不带 allow_images** 的密钥文件'
            '（claim-sync-env.yml）被误判为不合规 —— 判据 4 过宽了。'
        )

    # ⚠️ 同一条判据的**另一半**：脚本任务用 `settingsFrom` 引密钥，必须报错
    # （`settingsFrom` 是加载插件参数的语义，脚本任务没有插件参数）。
    bad_script_task_settingsfrom = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'name': '认领同步',
                            'image': 'python:3.12-slim',
                            'script': 'python scripts/bridge/claim_detect.py --apply',
                            'settingsFrom': [
                                'https://cnb.cool/o/secret/-/blob/main/claim-sync-env.yml'
                            ],
                        }
                    ]
                }
            ]
        }
    }
    if not check_secret_ref_on_script_task(bad_script_task_settingsfrom):
        errors.append(
            '自检探针失败：脚本任务用 `settingsFrom` 引密钥文件没被报错'
            ' —— `settingsFrom` 是插件参数语义，脚本任务上无意义。'
        )

    # ⚠️ 判据 1 的**第二条回归探针**：同一份密钥文件，**别处挂对、这一处挂错**。
    # 本仓所有 job 引的是同一个 `vars.yml`，所以「URL 只要在别处合规就放过」这条白名单
    # 会把判据 1 整个架空（2026-10-14 回退探针实测 MISSED，两次都栽在它上面）。
    bad_mixed = {
        'main': {
            'push': [
                {'stages': [{'image': 'tencentcom/git-sync', 'imports': ['https://x/vars.yml']}]}
            ]
        },
        '$': {'push': [{'imports': ['https://x/vars.yml'], 'stages': [{'image': 'tencentcom/http-request'}]}]},
    }
    if not check_pipeline_level_secret_refs(bad_mixed):
        errors.append(
            '自检探针失败：「别处挂对、这一处挂在 job 对象上」没被判据 1 报错'
            ' —— URL 级白名单又回来了（它会把判据 1 整个架空）。'
        )

    # 判据 1：流水线级 imports 引密钥。
    bad1 = {
        'main': {
            'push': [
                {
                    'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                    'stages': [{'image': 'tencentcom/git-sync', 'settings': {'username': 'x'}}],
                }
            ]
        }
    }
    if not check_pipeline_level_secret_refs(bad1):
        errors.append('自检探针失败：流水线级 imports 引密钥（#148 ①）没被判据 1 报错。')

    # 判据 2：settingsFrom 引密钥 + settings 用 ${VAR}。
    bad2 = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'settingsFrom': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settings': {'username': '${GIT_USERNAME}', 'password': '${GITHUB_PAT}'},
                        }
                    ]
                }
            ]
        }
    }
    if not check_settingsfrom_var_substitution(bad2):
        errors.append('自检探针失败：settingsFrom + ${VAR}（#148 ②）没被判据 2 报错。')

    # 判据 3：两种语义并存。
    bad3 = {
        'main': {
            'push': [
                {
                    'stages': [
                        {
                            'image': 'tencentcom/git-sync',
                            'imports': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                            'settingsFrom': ['https://cnb.cool/o/secret/-/blob/main/vars.yml'],
                        }
                    ]
                }
            ]
        }
    }
    if not check_pipeline_level_secret_refs(bad3):
        errors.append('自检探针失败：imports 与 settingsFrom 并存（判据 3）没被报错。')

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description='检查 git-sync 密钥引用是否挂在插件任务级且用 imports')
    ap.add_argument('--file', default=None, help='待检查文件（默认仓库根 .cnb.yml）')
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    path = Path(args.file) if args.file else root / '.cnb.yml'
    if not path.exists():
        print(f'⚠️ 找不到 {path}，跳过')
        return 0

    problems = self_check()
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        print(f'❌ {path} 不是合法 YAML：{exc}')
        return 1
    if not isinstance(data, dict):
        data = {}

    problems += check_pipeline_level_secret_refs(data)
    problems += check_settingsfrom_var_substitution(data)
    problems += check_secret_ref_on_script_task(data)

    if problems:
        print(f'❌ {path} 密钥引用位置检查未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print('✅ git-sync 密钥引用合规（插件任务级 imports）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
