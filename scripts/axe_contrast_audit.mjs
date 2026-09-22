#!/usr/bin/env node
/**
 * 真机 axe-core 对比度回归（design.md 强制约束：# 所有 CSS 变量（颜色）变更必须通过
 * axe-core 或 Lighthouse 进行对比度回归测试，禁止在无自动化验证的情况下修改 --text-* / 颜色变量）
 * ============================================================
 *
 * WHY 需要它（而不是复用 scripts/audit_text_contrast.mjs）
 * ------------------------------------------------------
 * 那个脚本是**纯静态**的：只认 `color: var(--token)`，背景按 `--bg-page` / `--bg-card` 两个基准估。
 * 它算不出「真实层叠之后的最终前景色 / 有效背景色」——渐变、半透明叠加、`color-mix()`、
 * 被更靠后的规则覆盖、被祖先背景影响，全都看不见。而 design.md 第 334 行要求的是
 * **axe-core 或 Lighthouse** 级别的回归。本脚本用官方 axe-core 在真浏览器里跑，补上这一层。
 *
 * 零新增依赖的实现方式
 * --------------------
 *   · 浏览器：系统 Edge（`--headless=new`）+ CDP。**不下载 chromium**（省 ~130MB / 省 CI 时间）。
 *   · 引擎：官方 axe-core 单文件（`axe.min.js`），从 CDN 拉一次后缓存到临时目录；也可 `--axe-file` 指定本地副本。
 *   · 传输：Node 22 内置 `WebSocket` / `fetch`（无需 puppeteer / playwright）。
 *   · 登录：注入一份结构完整、时间未过期的 Supabase 会话 cookie（格式与 frontend/e2e/support/session.ts 一致，
 *     base64url + `sb-<project-ref>-auth-token`），只为了让受保护路由能渲染出真实 DOM；**不打真实 Supabase**。
 *
 * 用法
 * ----
 *     node scripts/axe_contrast_audit.mjs                       # 亮色，默认路由集
 *     node scripts/axe_contrast_audit.mjs --theme dark          # 暗色
 *     node scripts/axe_contrast_audit.mjs --routes /explore,/profile --json out.json
 *     node scripts/axe_contrast_audit.mjs --base-url http://127.0.0.1:8848 --allow-violations
 *
 * 退出码：发现 color-contrast 违规 → 1（可配 `--allow-violations` 只看报告）。
 *
 * 已知边界：只跑 `color-contrast` / `color-contrast-enhanced` 两条规则（本脚本的存在目的就是颜色回归）；
 * 页面须已由 dev server 提供服务（本脚本**不**自己起 dev server，避免与手工调试端口打架）。
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import process from 'node:process';

// ---------------------------------------------------------------- 参数

const args = process.argv.slice(2);
const arg = (name, fallback = null) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const flag = name => args.includes(name);

const BASE_URL = arg('--base-url', 'http://127.0.0.1:8848').replace(/\/$/, '');
const THEME = arg('--theme', 'light');
const ROUTES = arg('--routes', '/explore,/login').split(',').map(s => s.trim()).filter(Boolean);
const JSON_OUT = arg('--json', null);
const AXE_VERSION = arg('--axe-version', '4.10.2');
const AXE_FILE = arg('--axe-file', null);
const ALLOW = flag('--allow-violations');
/** 不注入会话 cookie（用于 `/explore` `/login` 这类免登录路由——登录态下它们可能被改路由到首页）。 */
const NO_COOKIE = flag('--no-cookie');
/** 截图目录：共享组件的改动「一改全站变版」，数字之外必须留下可肉眼复核的证据。 */
const SHOT_DIR = arg('--shot', null);
const SETTLE_MS = Number(arg('--settle-ms', '5000'));
const PORT = Number(arg('--cdp-port', '9333'));
/** 与 frontend/.env 的 VITE_SUPABASE_URL 一致；仅用于推算 cookie 名，不需要真凭据。 */
const SUPABASE_URL = arg('--supabase-url', 'https://owhbssypqaghpnjoxlkx.supabase.co');

const EDGE_CANDIDATES = [
  process.env.AXE_BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/microsoft-edge',
].filter(Boolean);

const RULE_IDS = ['color-contrast', 'color-contrast-enhanced'];
/** 只有这条规则对应 WCAG AA（本项目门槛）；`-enhanced` 是 AAA，仅作参考、不卡门禁。 */
const GATING_RULE = 'color-contrast';

// ---------------------------------------------------------------- axe-core 取源

async function axeSource() {
  if (AXE_FILE) return readFileSync(AXE_FILE, 'utf8');
  const cached = join(tmpdir(), `axe-core-${AXE_VERSION}.min.js`);
  if (existsSync(cached)) return readFileSync(cached, 'utf8');
  const url = `https://cdn.jsdelivr.net/npm/axe-core@${AXE_VERSION}/axe.min.js`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`axe-core 下载失败 ${res.status}: ${url}`);
  const src = await res.text();
  if (src.length < 100_000) throw new Error(`axe-core 内容异常（${src.length} 字节），疑似代理返回了错误页`);
  writeFileSync(cached, src);
  return src;
}

// ---------------------------------------------------------------- 会话 cookie

/** 复刻 frontend/e2e/support/session.ts 的格式（该文件已对 @supabase/ssr 实测，非猜测）。 */
function supabaseCookie() {
  const ref = (() => {
    try {
      return new URL(SUPABASE_URL).hostname.split('.')[0];
    } catch {
      return 'e2etest';
    }
  })();
  const now = Math.floor(Date.now() / 1000);
  const session = {
    access_token: 'axe-audit-injected-access-token',
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: now + 3600,
    refresh_token: 'axe-audit-injected-refresh-token',
    user: {
      id: '00000000-0000-4000-8000-000000000000',
      aud: 'authenticated',
      role: 'authenticated',
      email: 'axe-audit@example.com',
      email_confirmed_at: new Date(now * 1000).toISOString(),
      created_at: new Date(now * 1000).toISOString(),
      user_metadata: { roles: ['user'], username: 'axe-audit', nickname: 'axe 审计' },
      app_metadata: { provider: 'email', providers: ['email'] },
    },
  };
  return {
    name: `sb-${ref}-auth-token`,
    value: `base64-${Buffer.from(JSON.stringify(session), 'utf8').toString('base64url')}`,
  };
}

// ---------------------------------------------------------------- CDP 最小客户端

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------------------------------------------------------------- 超时护栏（#1599）
// 本脚本此前在「CDP 就绪之后的等待段」**完全没有超时**：浏览器/页面一旦不回应就
// **长时间零输出**（实测 3 路由 × 2 主题跑 11 分钟、单路由 25 分钟，输出文件恒为 0 字节，
// 无报错、不退出），排查时无法判断卡在哪一步。下面三处等待全部加超时，并在超时消息里
// 附带现场诊断（CDP 往返轨迹 + Edge stderr 尾巴），慢机器可用环境变量放宽：
//   AXE_WS_TIMEOUT_MS（默认 20000）/ AXE_CDP_TIMEOUT_MS（默认 30000）/ AXE_EVAL_TIMEOUT_MS（默认 60000）
const envNum = (v, d) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);
const WS_TIMEOUT_MS = envNum(process.env.AXE_WS_TIMEOUT_MS, 20000);
const CDP_TIMEOUT_MS = envNum(process.env.AXE_CDP_TIMEOUT_MS, 30000);
const EVAL_TIMEOUT_MS = envNum(process.env.AXE_EVAL_TIMEOUT_MS, 60000);

function withTimeout(promise, ms, label, onTimeout) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, rej) => {
      timer = setTimeout(() => {
        try {
          onTimeout?.();
        } catch {
          /* 诊断自身出错不影响结论 */
        }
        rej(new Error(`⏱ 超时(${ms}ms)：${label}`));
      }, ms);
    }),
  ]).finally(() => clearTimeout(timer));
}

async function connectCDP(onLog = console.error) {
  const bin = EDGE_CANDIDATES.find(p => existsSync(p));
  if (!bin) throw new Error(`未找到浏览器可执行文件，试过：\n  ${EDGE_CANDIDATES.join('\n  ')}\n可用 AXE_BROWSER 指定`);
  const profile = mkdtempSync(join(tmpdir(), 'axe-edge-'));
  const proc = spawn(
    bin,
    [
      '--headless=new',
      '--disable-gpu',
      // 本地审计必须绕开系统代理：本机装了 DevSidecar（127.0.0.1:31180/31181），
      // 它会把对 127.0.0.1 的请求也代理掉，实测表现为页面加载 502、
      // 脚本**长时间零输出**（11 分钟无结果，看起来像卡死，实际是页面永远加载不出来）。
      // 审计目标是本地 dev server，走代理没有任何意义，故显式关闭。
      '--no-proxy-server',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${profile}`,
      'about:blank',
    ],
    { stdio: ['ignore', 'ignore', 'pipe'] }
  );

  let targets = null;
  for (let i = 0; i < 60; i++) {
    await sleep(500);
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      if (r.ok) {
        targets = await r.json();
        break;
      }
    } catch {
      /* 未就绪，继续等 */
    }
  }
  if (!targets) {
    proc.kill();
    throw new Error(`CDP ${PORT} 端口未就绪（浏览器是否被沙箱拦截？）`);
  }
  const page = targets.find(t => t.type === 'page');
  if (!page) {
    proc.kill();
    throw new Error('没有可用的 page target');
  }

  // 诊断现场（#1599）：CDP 往返轨迹 + Edge stderr 尾巴。
  // stderr 原为 'pipe' 却**无人读取** —— 管道缓冲写满后浏览器会阻塞（经典死锁），
  // 这里持续排空并只保留末尾若干行，超时/失败时随消息一起抛出。
  const cdpTrail = [];
  const stderrTail = [];
  proc.stderr?.on('data', chunk => {
    for (const line of String(chunk).split('\n')) {
      if (line.trim()) stderrTail.push(line.trim());
    }
    if (stderrTail.length > 60) stderrTail.splice(0, stderrTail.length - 60);
  });

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let seq = 0;
  let wsOpen = false;
  const pending = new Map();
  const diagnostics = () =>
    [
      `浏览器: ${bin}`,
      `CDP 往返轨迹（最近 8 条）: ${cdpTrail.slice(-8).join(' | ') || '（无）'}`,
      `WebSocket: ${wsOpen ? 'open' : '未触发 open'}`,
      `Edge stderr 尾巴（最近 8 行）: ${stderrTail.slice(-8).join(' / ') || '（无）'}`,
    ].join('\n    ');

  ws.addEventListener('message', ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  });
  await withTimeout(
    new Promise((res, rej) => {
      ws.addEventListener(
        'open',
        () => {
          wsOpen = true;
          res();
        },
        { once: true }
      );
      ws.addEventListener('error', rej, { once: true });
    }),
    WS_TIMEOUT_MS,
    `WebSocket 未在 ${WS_TIMEOUT_MS}ms 内 open（CDP 就绪但不接受调试连接？）\n    ${diagnostics()}`
  );

  const send = (method, params = {}, timeoutMs = CDP_TIMEOUT_MS) => {
    const id = ++seq;
    cdpTrail.push(`${method}#${id}`);
    if (cdpTrail.length > 60) cdpTrail.shift();
    const reply = withTimeout(
      new Promise(res => pending.set(id, res)),
      timeoutMs,
      `CDP 命令无响应：${method}（页面是否卡在加载？）\n    ${diagnostics()}`,
      () => pending.delete(id) // 超时后清理，避免悬挂条目
    ).then(r => {
      if (r?.error) throw new Error(`CDP 返回错误：${method} → ${r.error.message ?? JSON.stringify(r.error)}`);
      return r;
    });
    // #1599 根因修复：这里**必须把命令真正写进 WebSocket**。此前只登记了 pending 与轨迹、
    // 却漏了 `ws.send`，表现为「WS 正常 open、readyState=1 挂满超时、零回帧」——而且没有任何
    // 报错、输出恒 0 字节（超时护栏正是把它从「静默挂死」变成「30 秒报错」的那层）。
    // 顺序上先注册 pending 再发送，回包不可能先于登记到达。
    if (ws.readyState !== 1) {
      throw new Error(`CDP 连接不可用（readyState=${ws.readyState}），无法发送 ${method}`);
    }
    ws.send(JSON.stringify({ id, method, params }));
    return reply;
  };

  const evaluate = async expression => {
    // awaitPromise=true 时 CDP 会一直等页面内的 Promise 结束 —— 页面卡住就永不返回，
    // 故这一条单独放宽容忍（EVAL_TIMEOUT_MS，默认 60s）并保留现场诊断。
    const r = await send(
      'Runtime.evaluate',
      { expression, returnByValue: true, awaitPromise: true },
      EVAL_TIMEOUT_MS
    );
    if (r.result?.exceptionDetails) {
      throw new Error(`页面内求值抛错：${r.result.exceptionDetails.text ?? ''} ${r.result.result?.description ?? ''}`);
    }
    return r.result?.result?.value;
  };

  const close = async () => {
    try {
      ws.close();
    } catch {
      /* ignore */
    }
    proc.kill();
    await sleep(600);
    // Crashpad 会短暂占用 profile 目录里的文件 —— 清理失败不影响结论，忽略即可
    for (let i = 0; i < 3; i++) {
      try {
        rmSync(profile, { recursive: true, force: true });
        break;
      } catch {
        await sleep(500);
      }
    }
  };

  return { send, evaluate, close, bin, diagnostics };
}

// ---------------------------------------------------------------- 主流程

const axe = await axeSource();
const { send, evaluate, close, bin } = await connectCDP();

const results = [];
try {
  await send('Page.enable');
  await send('Network.enable');
  await send('Runtime.enable');
  // 首屏就把 axe 装上，避免「注入太晚、DOM 已变」的时序坑
  await send('Page.addScriptToEvaluateOnNewDocument', { source: axe });
  const cookie = supabaseCookie();
  if (!NO_COOKIE) {
    await send('Network.setCookie', { name: cookie.name, value: cookie.value, url: BASE_URL });
  }

  for (const route of ROUTES) {
    // 本应用是 **hash 路由**：真实路由在 `location.hash`。写成 `/explore` 会被当成 `/`，
    // 进而被守卫重定向到 `#/login`——实测踩过，故统一拼成 `/#<route>`。
    const url = `${BASE_URL}/#${route.replace(/^#/, '')}`;
    const wantHash = `#${route.replace(/^#/, '')}`;
    // 先回 about:blank：否则 `document.readyState` 会拿上一页的 'complete' 立刻通过轮询，
    // 结果是「量到了上一页的 DOM」（实测：/login 与 /explore 的违规逐字节相同，含 scoped 属性哈希）。
    await send('Page.navigate', { url: 'about:blank' });
    await sleep(300);
    await send('Page.navigate', { url });
    let landed = null;
    for (let i = 0; i < 80; i++) {
      await sleep(250);
      const state = await evaluate(`location.href + '|' + document.readyState`);
      if (typeof state === 'string' && state.endsWith('|complete') && state.split('|')[0].includes(wantHash)) {
        landed = state.split('|')[0];
        break;
      }
    }
    if (!landed) console.error(`  !! ${route} 未在 20s 内落到 ${wantHash}，结论可能不可信`);
    // 留出异步取数 / 渲染 / 动画的稳定时间
    await sleep(SETTLE_MS);
    await evaluate('window.scrollTo(0, document.body.scrollHeight); 1'); // 触发懒加载/滚动进入视口的块
    await sleep(1200);
    await evaluate('window.scrollTo(0, 0); 1');
    if (THEME === 'dark') {
      await evaluate(
        `document.documentElement.classList.add('dark');` +
          `document.documentElement.setAttribute('data-theme','dark');` +
          `document.body.dispatchEvent(new Event('theme-change'));` +
          `1`
      );
      await sleep(1200);
    }

    const finalUrl = await evaluate('location.pathname + location.search');
    // 截图（全页）：`--shot <dir>` 时按 theme+route 落盘，供人眼复核共享组件的改动。
    // 先临时抬高视口再截：后台布局是「固定外壳 + 内部滚动」，否则只能拿到 487px 的视口高度。
    if (SHOT_DIR) {
      await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 2400, deviceScaleFactor: 1, mobile: false });
      await sleep(900);
      const metrics = await send('Page.getLayoutMetrics');
      const h = Math.min(Math.ceil(metrics.result?.cssContentSize?.height ?? 2400), 6000);
      const shot = await send('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: 1280, height: h, scale: 1 },
      });
      await send('Emulation.clearDeviceMetricsOverride');
      const name = `${THEME}_${route.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '') || 'root'}.png`;
      writeFileSync(join(SHOT_DIR, name), Buffer.from(shot.result?.data ?? '', 'base64'));
      console.log(`  📷 ${join(SHOT_DIR, name)}  (${h}px)`);
    }
    // 「量到的是哪个页面」必须自证：dev 构建带 code-inspector，data-insp-path 就是真实源文件路径。
    const context = await evaluate(
      `(() => {` +
        ` const paths = [...new Set([...document.querySelectorAll('[data-insp-path]')]` +
        `   .map(el => (el.getAttribute('data-insp-path') || '').split(':')[0]))];` +
        ` return JSON.stringify({ title: document.title, url: location.href,` +
        `   inspFiles: paths.slice(0, 6), inspCount: paths.length, nodes: document.querySelectorAll('*').length });` +
        ` })()`
    );
    const shot = await evaluate(
      `(() => { const r = axe.run(document, { runOnly: { type: 'rule', values: ${JSON.stringify(RULE_IDS)} } });` +
        ` return r.then(v => JSON.stringify(v.violations.map(x => ({` +
        `   id: x.id, impact: x.impact, help: x.help, nodes: x.nodes.map(n => ({` +
        `     target: n.target, html: n.html, summary: n.failureSummary,` +
        `     data: n.any && n.any[0] ? n.any[0].data : null,` +
        `   })),` +
        ` })))).catch(e => JSON.stringify([{ id: '__error__', impact: 'error', help: String(e && e.message || e), nodes: [] }])); })()`
    );
    const violations = JSON.parse(shot ?? '[]');
    const ctx = JSON.parse(context ?? '{}');
    results.push({ route, finalUrl, context: ctx, violations });
    const aa = violations.filter(v => v.id === GATING_RULE);
    const aaa = violations.filter(v => v.id !== GATING_RULE);
    const count = aa.reduce((n, v) => n + v.nodes.length, 0);
    console.log(`\n=== ${THEME} ${route}  (落在 ${finalUrl}) ===`);
    console.log(`  页面自证: title="${ctx.title}" url=${ctx.url}`);
    console.log(`  渲染来源: ${(ctx.inspFiles ?? []).join(' | ') || '（无 data-insp-path，可能非 dev 构建）'}  节点数=${ctx.nodes}`);
    if (!aa.length) {
      console.log(`  ✅ color-contrast（AA）无违规`);
    } else {
      for (const v of aa) {
        console.log(`  ✗ ${v.id} [${v.impact}] ${v.help} — ${v.nodes.length} 个节点`);
        for (const n of v.nodes) {
          const d = n.data ?? {};
          console.log(
            `      ${Array.isArray(n.target) ? n.target.join(' ') : n.target}` +
              `  fg=${d.fgColor ?? '?'} bg=${d.bgColor ?? '?'}` +
              `  实测 ${d.contrastRatio ?? '?'} / 需 ${d.expectedContrastRatio ?? '?'}` +
              `  [${d.fontSize ?? '?'} ${d.fontWeight ?? '?'}]`
          );
          if (d.contrastRatio == null) console.log(`      ${String(n.summary ?? '').split('\n')[0]}`);
          // HTML 片段：定位「这条规则到底来自哪个组件/模板」，比选择器路径更快
          console.log(`      html: ${String(n.html ?? '').replace(/\s+/g, ' ').slice(0, 160)}`);
        }
      }
    }
    for (const v of aaa) {
      console.log(`  · ${v.id}（AAA，仅参考）— ${v.nodes.length} 个节点，未达 7:1`);
    }
  }
} finally {
  await close();
}

console.log(
  `\n浏览器: ${bin}\naxe-core: ${AXE_VERSION}\nbase: ${BASE_URL}\ntheme: ${THEME}\nroute: ${ROUTES.join(', ')}`
);

const total = results.reduce(
  (n, r) => n + r.violations.filter(v => v.id === GATING_RULE).reduce((m, v) => m + v.nodes.length, 0),
  0
);
if (JSON_OUT) {
  writeFileSync(JSON_OUT, `${JSON.stringify({ meta: { baseUrl: BASE_URL, theme: THEME, axeVersion: AXE_VERSION, browser: bin }, results }, null, 2)}\n`);
  console.log(`报告已写入 ${JSON_OUT}`);
}
console.log(total === 0 ? '结论：AA 门槛 0 违规' : `结论：AA 门槛 ${total} 个节点违规`);
process.exit(total === 0 || ALLOW ? 0 : 1);
