/**
 * `scripts/axe_contrast_audit.mjs` 的回归用例（#1599）。
 *
 * WHY 有这份文件
 * --------------
 * 这个「真机 axe」审计器是 #1599 的**验收工具**（AC1：亮/暗双档覆盖主要路由、违规归零）。
 * 但在 2026-09-22 之前它**从未产出过任何结论**：实测跑 11~25 分钟、输出恒 0 字节、
 * 无报错、不退出。当时按现象猜过三个方向（WS 未 open / 端口死锁 / 代理把页面打成 502），
 * 逐一实测都不成立；真正的根因在 CDP 客户端：
 *
 *     send() 只登记了 pending 与往返轨迹，**漏掉了 `ws.send`** —— 命令根本没写进 WebSocket。
 *
 * 于是症状恰好是：WS 正常 open、`readyState` 一直为 1、零回帧、挂到超时（旧版本没有超时，
 * 就是「静默挂死」）。这类缺陷最坏的地方是**没有任何报错**：没有任何人知道工具在空转，
 * 而人会拿它的结论当验收依据。
 *
 * 故本文件钉两层：
 *   ① **命令必须真的发出去**（根因回归）；
 *   ② **发不出去时不许静默**（超时护栏与现场诊断不得被删回去——它们是把「静默」变成
 *      「30 秒报错并交代卡在哪一步」的那一层）。
 *
 * 为什么是**源码级**断言，而不是子进程跑真脚本
 * -------------------------------------------
 * 真机运行需要系统 Edge + 一个可访问的 dev server（CI 上没有）；伪造一个 CDP 服务端需要
 * 自己实现 WebSocket 服务端握手与帧解析，成本远大于收益。所以这里钉的是**发送路径的结构
 * 约束**（不可退化的最小形态），真实行为由本地/手工跑覆盖——本次已实跑通过：
 * `node scripts/axe_contrast_audit.mjs --routes /profile` 正常产出 4 处 AA 违规明细与截图。
 *
 * 怎么跑：`pnpm test:scripts`（或 `node --test "scripts/tests/*.test.js"`）。零新依赖。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(resolve(HERE, '..', 'axe_contrast_audit.mjs'), 'utf8');

/** 取 `const send = (…) => { … };` 的函数体（以下一个顶层定义为界，避免误配到别处）。 */
function sendBody() {
  const start = SRC.indexOf('const send = (method');
  assert.ok(start > 0, '未找到 send() 定义：结构变了请同步本用例，而不是删掉断言');
  const end = SRC.indexOf('const evaluate = ', start);
  assert.ok(end > start, '未找到 send() 之后的下一个顶层定义，无法定界函数体');
  return SRC.slice(start, end);
}

test('根因回归：send() 必须把命令真正写进 WebSocket（此前漏了 ws.send → 零回帧、恒 0 字节）', () => {
  const body = sendBody();
  assert.match(
    body,
    /ws\.send\(\s*JSON\.stringify\(\s*\{\s*id\s*,\s*method\s*,\s*params\s*\}\s*\)\s*\)/,
    'send() 里必须有 ws.send(JSON.stringify({ id, method, params }))；' +
      '缺了它，命令只被登记、从不发出，表现为 WS 正常 open 但零回帧（#1599 根因）'
  );
});

test('发送前先注册 pending：回包不可能先于登记到达', () => {
  const body = sendBody();
  const registered = body.indexOf('pending.set(id');
  const sent = body.indexOf('ws.send(');
  assert.ok(registered > 0, 'send() 必须先注册 pending');
  assert.ok(sent > registered, '顺序应为「先 pending.set、后 ws.send」，否则极快回包会丢');
});

test('连接不可用时显式抛错，不得静默等待（静默是最坏形态）', () => {
  assert.match(
    sendBody(),
    /ws\.readyState\s*!==\s*1/,
    '发送前须检查 readyState 并在不可用时抛错，让「发不出去」立刻可见'
  );
});

test('超时护栏的三处默认值不得删回去（删了就回到「静默挂死」）', () => {
  assert.match(SRC, /AXE_WS_TIMEOUT_MS/, 'WebSocket open 等待必须有超时且可用环境变量放宽');
  assert.match(SRC, /AXE_CDP_TIMEOUT_MS/, 'CDP 命令等待必须有超时');
  assert.match(SRC, /AXE_EVAL_TIMEOUT_MS/, 'Runtime.evaluate 等待必须有超时');
  assert.match(SRC, /AXE_WS_TIMEOUT_MS['"]?,\s*20000|,\s*20000\s*\)/, 'WS 默认 20s');
  assert.match(SRC, /AXE_CDP_TIMEOUT_MS['"]?,\s*30000|,\s*30000\s*\)/, 'CDP 默认 30s');
  assert.match(SRC, /AXE_EVAL_TIMEOUT_MS['"]?,\s*60000|,\s*60000\s*\)/, 'evaluate 默认 60s');
});

test('超时/失败必须带现场诊断（CDP 往返轨迹 + WebSocket 状态 + Edge stderr 尾巴）', () => {
  const body = sendBody();
  assert.match(body, /CDP 命令无响应/, 'CDP 超时消息须点名是哪条命令');
  assert.match(body, /diagnostics\(\)/, '超时消息须嵌入现场诊断，否则又变成「卡在哪一步靠猜」');
  assert.match(SRC, /cdpTrail/, '须保留 CDP 往返轨迹');
  assert.match(SRC, /stderrTail/, '须保留 Edge stderr 尾巴（原为 pipe 却无人读，缓冲写满会阻塞浏览器）');
});

test('CDP 返回 error 时必须抛出，不得当成功继续（否则会拿上一页/空 DOM 出结论）', () => {
  assert.match(
    sendBody(),
    /r\?\.error[\s\S]{0,80}throw new Error/,
    '响应里的 error 字段必须转成异常，避免「错了却继续跑」'
  );
});
