/**
 * `scripts/tests/` 下**唯一**一份 Python 解释器探测（源 #119；2026-10-24 收敛为单一真相）。
 *
 * ## 为什么不能写死解释器名（踩坑记录，别再走一遍）
 *
 * 这些回归网靠**子进程跑 Python 守卫脚本**。它们原先都写死
 * `process.env.PYTHON || "python"`，而 `python` 这个命令**不是处处都有**
 * （Debian/Ubuntu 只有 `python3`；本仓 CNB 工作区、WSL、多数容器皆如此）。
 *
 * 后果不是「报错」，而是**静默绿**：`spawnSync` 抛 ENOENT，被 `catch` 拼成
 * `"spawnSync python ENOENT"` 返回，里面既没有命中标记也没有 `Traceback`，于是：
 *
 *   - 「必须命中」的断言失败（19/30、9/16）；
 *   - 「必须放行」的断言**全部假通过** —— 它们断言的是「输出里没有某标记」，
 *     而「什么都没跑」恰好满足这一条。
 *
 * 2026-10-11 实测：同一份代码只把 `python` 换成 `python3`，18 fail → 0 fail。
 * 这 18 个红灯在 CI（ubuntu-latest 自带 python 别名）上永远不出现，本地却成片出现，
 * 每次都要人工判断「这 18 个要不要紧」——红灯可信度就是这样被消耗掉的。
 *
 * ## 为什么收成一份（而不是每个文件各写一份）
 *
 * 到 2026-10-24，仓里有 **6 份**逐字雷同的 `findPython()` 拷贝，另有 4 个文件干脆
 * 硬写 `"python3"`（连探测都没有）。拷贝的问题不在于「重复」，而在于**改不齐**：
 * 修一次只修到一份，剩下的继续假绿，而 `guard_python_interpreter.test.js` 当时只盯
 * 得动手写名单里的 3 个文件——名单外的漏点它是完全看不见的。
 *
 * 现在：探测逻辑只此一份，判据改成「从源码推导 + 必须接线到本模块」，名单不再手写
 * （见 `guard_python_interpreter.test.js`）。
 *
 * ## 候选顺序与理由
 *
 * 1. `$PYTHON` —— 显式指定优先。**但它可能指向不存在的路径**，所以必须继续往下试，
 *    而不是「设了就用」（判据 ② 正是钉这一条：设错环境变量不该得到「找不到解释器」的
 *    错误结论）。
 * 2. Windows：`python` → `py -3`。`py` 是 Windows 官方的版本选择器，`py -3` 才是它的
 *    正常调用形态（`py` 单独跑会走默认版本，行为随安装选择变化）；有些安装里 `python`
 *    是 Microsoft Store 的桩程序，退出码非 0，会被下面的「status === 0」自然跳过。
 * 3. 其它平台：`python3` → `python`。
 *
 * 想加候选（例如 Windows 上的 `python3`、conda 路径）**只改这里**，不要回到各文件去抄。
 *
 * ## 「找不到」时怎么办
 *
 * 一律 `pythonOrFail()` —— **抛错**，不许 skip、不许静默放行。「解释器不在」与
 * 「判据没命中」是两件事，必须报出前者：把前者当成后者，就是本文件开头那段假绿。
 */

import { spawnSync } from "node:child_process";

/*
 * 让**子进程**的 Python 强制走 UTF-8（沿用外部显式设置：已设则不覆盖）。
 *
 * 为什么在这里做：这些守卫脚本会往 stdout 打印中文与 `❌` 之类的符号，而 Windows 的
 * 默认控制台编码是 cp936，`print()` 到**管道**时会抛
 * `UnicodeEncodeError: 'gbk' codec can't encode character '\u274c'` —— 退出码 1、
 * stdout 空。对调用方来说，这与「守卫判定不通过」**长得一模一样**，但其实是无声崩溃
 * （2026-10-24 实测：不设它，本机这 30 条回归网全红；设上即 0 fail）。
 *
 * 崩溃本身出在 `scripts/*.py`（本目录不改那些文件），所以只能在**启动方**统一
 * 归一化环境变量；放在本模块是为了只归一化一次，而不是每个 spawnSync 各写一遍。
 */
process.env.PYTHONUTF8 ??= "1";
process.env.PYTHONIOENCODING ??= "utf-8";

/**
 * 探测可用的 Python 解释器。
 *
 * @returns {[string, ...string[]] | null} `[命令, ...固定参数]`（如 `["py", "-3"]`），
 *   直接可喂给 `spawnSync(found[0], [...found.slice(1), ...])`；找不到返回 `null`。
 */
function findPython() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push([process.env.PYTHON]);
  if (process.platform === "win32") {
    candidates.push(["python"], ["py", "-3"]);
  } else {
    candidates.push(["python3"], ["python"]);
  }
  for (const args of candidates) {
    const r = spawnSync(args[0], [...args.slice(1), "--version"], { encoding: "utf8" });
    if (!r.error && r.status === 0) return args;
  }
  return null;
}

/**
 * 取解释器，取不到就**显式抛错**（调用方只在模块顶层调用它，于是整份文件在加载期就失败）。
 *
 * 为什么必须抛而不是 `return null` 让调用方 `skip`：`node --test` 里 skip 的用例既不算
 * 通过也不算失败，退出码仍是 0 —— 对 CI 和对人都是「绿」。而守卫脚本根本没跑过，
 * 「必须放行」的断言因此恒真，等于这道门从来没关过。
 *
 * 平移到别的脚本时注意：抛错必须发生在**模块顶层**（`const PY = pythonOrFail()`），
 * 不能包在用例体里 —— 用例体里抛只会让 M 个用例各红一次，而「一个解释器都没有」这件事
 * 应当在读到 `ℹ pass` 之前就说清楚。
 *
 * @returns {[string, ...string[]]} 同 `findPython()` 的返回值，保证非空。
 */
function pythonOrFail() {
  const found = findPython();
  if (!found) {
    throw new Error(
      "找不到 Python 解释器（试过 $PYTHON / python3 / python；Windows 上还有 py -3）。\n" +
        "本文件的断言都靠子进程跑 Python 守卫脚本；解释器缺席时「必须放行」的断言会因\n" +
        "「什么都没跑」而全部假通过（#119 那批 18 个假绿就是这么来的）。\n" +
        "请安装 Python，或把解释器路径写进 $PYTHON 环境变量。"
    );
  }
  return found;
}

export { findPython, pythonOrFail };
