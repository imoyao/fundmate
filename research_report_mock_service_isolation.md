# fundmate Mock 服务与数据隔离方案调研报告

## 执行摘要

可以为 fundmate 引入 mock 服务来实现你的两个目标，而且绝大多数核心方案都是免费的。你的诉求其实分两层：第一层「避免污染数据库」靠在 API 层做 mock，让测试/开发请求根本不进入真实后端与数据库；第二层「环境隔离、不污染云端 Supabase」靠为开发/测试创建独立的 Supabase 环境（本地 Docker 或独立 dev 项目）并用环境变量切换。调研同时确认了一个现状问题：本仓库当前开发环境与生产环境其实共用同一个云端 Supabase 项目，隔离并未真正建立，本报告给出了修复骨架。

## 背景与现状

fundmate（多多贝）是前后端分离的个人投资记账平台：后端 Flask/APIFlask，主数据用本地 SQLite；前端 Vue 3 + Vite（pure-admin）；身份认证已接入 Supabase Auth（云端数据库），后端仅做 JWT 验签与白名单鉴权。你的两条诉求分别对应两个不同的数据源：本地 SQLite（主数据）和云端 Supabase（登录/注册等 Auth）。要避免污染，就要让「测试/开发」与「生产」各自碰到不同的数据源。

调研中核实了本仓库前端的环境配置，发现隔离目前是缺失的：`frontend/.env`（Vite 中所有模式都会加载该文件）与 `frontend/.env.development` 都写入了同一个云端 Supabase 项目 `https://owhbssypqaghpnjoxlkx.supabase.co` 的 URL 与 anon key，而 `frontend/.env.production` 没有 Supabase 配置。由于 Vite 的加载优先级是 `.env` 低于 `.env.production` 但后者未定义 Supabase 项，生产构建实际上沿用了 `.env` 里的开发用 Supabase 配置。也就是说，开发、测试、生产目前指向同一个云端 Auth 项目，这正是你感受到的「混在一块儿」。anon key 本身属公开设计（受 RLS 保护），但环境未分离意味着任何测试注册都会写进同一个线上 Auth 用户表。

## 一、什么是 mock 服务，能否满足你的诉求

mock 服务的本质是「在请求到达真实后端之前就返回假数据」。它天然满足你的第一层诉求：当 mock 发生在前端网络层（浏览器 Service Worker 拦截）或独立的本地 mock server 时，真实的 Flask 路由、ORM 与底层数据库完全不会收到请求、不会执行任何写入，哪怕是 POST/PUT/DELETE 也只在 mock 层的内存或 JSON 文件里生效。因此「避免污染数据库」不需要反复手工调数据，只要把前端请求指向 mock 即可。

对于你的第二层诉求（不污染云端 Supabase），mock 服务本身只能解决「前端不发真实请求」，但 Auth 的注册/登录调用仍可能命中云端。这部分需要用 Supabase 自身的环境隔离（下文第四节）来兜底，二者配合才能彻底隔离。

结论：有这类 mock 服务，而且方案成熟（回答 c 为「有」）。

## 二、工具与服务全景对比（免费优先）

下表汇总了可用于「前端联调/测试不碰真实后端」的主流工具，按免费优先、能离线优先排列。所有工具在 2024–2026 年均处于活跃维护状态。

| 工具 | 本地/托管 | 免费额度 | 拦截层级 | 是否需编码 | 适用场景 |
|------|----------|---------|---------|-----------|---------|
| Mockoon（桌面/CLI） | 本地（开源 MIT） | 完全免费，无限制 | 独立 mock server + 代理模式 | 否（GUI 可视化） | 快速本地 mock，零代码，离线 |
| json-server | 本地（开源 MIT） | 完全免费，无限制 | 独立 REST server | 否（写 db.json） | 简单 REST 假数据，零编码 |
| Prism（Stoplight） | 本地（开源 Apache-2.0） | 完全免费，无限制 | 独立 server / 代理 | 否（OpenAPI 驱动） | 已有 OpenAPI/Swagger 即出 mock |
| MSW | 本地（库，MIT） | 完全免费 | 前端网络层（Service Worker） | 是（写 JS/TS handler） | 前端开发/单测，彻底隔离后端 |
| Mirage JS | 本地（库，MIT） | 完全免费 | 前端网络层（fetch 补丁）+ 内存 ORM | 是（写 JS） | 前端带内存库的复杂模拟 |
| WireMock OSS | 本地（开源 Apache-2.0） | 完全免费，无限制 | 独立 server / 代理/录制 | 部分（JSON 映射，需 Java） | 复杂/状态化 mock、契约测试 |
| Postman Mock | 托管+本地 | 免费版含无限本地/云端 mock server（需账号，限 1 用户） | 独立 mock server | 否（UI） | 已有 Postman Collection 的团队 |
| Beeceptor | 托管 | 永久免费：50 请求/天、3 条 rules、CRUD 存 10 个小对象（免注册） | 独立云端 mock server | 否（UI） | 快速云端假 API、演示 |
| Mocky（mockyapi.org） | 本地桌面（开源） | 完全免费，无请求/天数限制 | 独立本地 mock server | 否（GUI） | 离线桌面 mock，零注册 |
| Stoplight | 托管 | Free：1 项目、1 用户（含自动/本地 mock） | 独立/本地 mock server | 否（OpenAPI 驱动） | API 设计+文档+mock 一体 |
| Apifox | 桌面（国产） | 免费版可用，桌面端支持 Mock | 独立 mock server（文档驱动） | 否（UI） | 中文团队一体文档+Mock+调试 |
| Requestly | 本地桌面+云 | 免费：10 协作者、无限本地项目、3 团队项目 | HTTP 拦截/重定向 | 部分（规则+脚本） | 请求拦截调试、临时切流 |
| WireMock Cloud | 托管 | 免费仅 1,000 调用/月、3 个 API、单用户 | 独立云端 mock server | 部分 | 不想自托管 WireMock 的团队 |
| Mockoon Cloud | 托管 | 无免费档（Team $100/月） | 云端 mock server | 否 | 团队云协作（非免费优先） |

需要说明的几点事实：json-server 的 1.x 至今仍是 beta（1.0.0-beta.15 约 2026-06 发布），正式项目建议锁 v0.17 稳定版；Mockoon Cloud 与 WireMock Cloud 的免费额度很小或没有，自托管的 OSS 版本才免费无限；Apifox 的 Mock 能力需在桌面版使用，WEB 版不支持 Mock。微信公众号「前端工匠」的文章《前端 Mock 数据方案，我是如何选择的？》（2023-11-20）也指出 MSW 与 Mock.js 是前端 Mock 的主流选型，与上方对比一致。

## 三、针对「避免污染数据库」的推荐

最彻底的隔离发生在前端网络层。推荐组合是 MSW 为主、Mockoon 为辅：

MSW（Mock Service Worker）装进 Vue 3 项目后，在 Vite 开发服务器下用 Service Worker 拦截 `fetch`/`axios` 请求，前端联调与单测拿到的都是假数据，请求永不离开浏览器，因此 Flask 后端和 SQLite 数据库零流量、零写入。它免费、可离线、对业务代码无侵入（不需要改请求地址），最适合「测试/开发时不污染真实数据库」这一硬性目标。

Mockoon 适合团队里不想写代码的成员：用桌面 GUI 可视化建一个本地 mock server，把前端的 `VITE_API_BASE` 指向 `localhost:某端口` 即可，同样离线、免费、无需账号。如果后端已经维护 OpenAPI/Swagger 文档，则优先用 Prism（`prism mock openapi.yaml`）一条命令起本地 mock，前后端按契约并行开发。

落地建议：在 Vite 中通过 `.env` 开关默认启用 MSW（仅 development/test 启用，production 构建关闭），配合 Mockoon 提供团队共享的本地 mock 环境；数据库侧再为测试配置独立 SQLite 文件，与 mock 形成双保险。测试用的假数据（`db.json` 或 MSW handlers）可随仓库提交，避免「不停调整数据」。

## 四、针对「环境隔离、不污染云端 Supabase」的推荐

这一层不靠 mock 工具，而靠 Supabase 自身的环境与依赖隔离。Supabase 以「项目（Project）」为单位完全隔离数据库、Auth 用户表、Storage 与密钥，不同项目有独立的域名、anon/service_role 密钥与 JWT 签名。Free tier 最多 2 个活跃项目、数据库 500 MB、出站流量 5 GB/月、Auth MAU 5 万、API 请求无限，但免费项目 7 天无活动会自动暂停。

方案一（推荐、零成本）：用 Supabase CLI 在本地起一套完整栈。`npx supabase init` 初始化（生成可提交的 `supabase/config.toml`），`npx supabase start` 通过 Docker 启动 Postgres + Auth + Storage + Studio + Mailpit，其中 Auth/API 在 `http://127.0.0.1:54321`、Postgres 在 `54322`、Studio 在 `54323`、邮件测试在 `54324`。本地栈免费、可离线（首次需联网拉镜像），注册登录走本地、邮件不真实外发，完全不写云端。切换只需把环境变量从 `https://<id>.supabase.co` 改为 `http://127.0.0.1:54321`，无需改业务代码。微信公众号「良辰美」的《Serverless 数据库三剑客 Supabase vs Neon vs Turso》（2026-01-31）也给出了 development / staging / preview 的分环境结构，与本地开发思路一致。

方案二（需付费才稳）：在独立组织建一个 Free 云端 dev 项目，env 单独指向它。会写云端但只写 dev 项目、不污染 prod；缺点是占 1 个免费额度且 7 天不活跃会暂停，若要「永久不暂停」需升级 Pro（$25/月起）。

方案三（测试零网络）：把 Supabase 客户端抽象成一个可替换的依赖（AuthProvider 接口），单元测试注入内存 fake（直接返回 `{ sub: 'test-user' }`），集成测试再起本地栈验证 JWT 验签链路。后端只验签不出 Auth 逻辑，依赖注入 + 本地栈即可保证全程不碰 prod 云数据库。JWT 验签建议用 `jose` 配合 JWKS（`createRemoteJWKSet` 指向 `/auth/v1/.well-known/jwks.json`），本地若用固定 jwt_secret 也可用 `jsonwebtoken` 自签 token 喂给验签逻辑做链路验证。

成本结论：dev 用本地 Docker、prod 用 1 个免费云端项目，合计 $0；只有「想要云端 dev 项目永久不暂停」才需付费。

## 五、环境变量隔离骨架与当前仓库修复

前端（Vite）用 `.env` / `.env.local` / `.env.[mode]` / `.env.[mode].local` 控制，只有 `VITE_` 前缀的变量才会进入客户端代码；`import.meta.env.MODE` 标识当前模式。后端（Flask）用 `pydantic-settings` 的 `BaseSettings` 做类型安全配置中心，按 `APP_ENV` 加载 `.env.<env>`。用一个总开关 `APP_ENV=development|production`（前端对应 `VITE_APP_ENV`）驱动前后端分别加载不同配置，实现 Server 端与 Product 端彻底隔离。

针对本仓库已确认的隔离缺失，建议做两处修复：其一，把 Supabase 配置从 `.env`（全模式加载）移出，分别写入 `.env.development`（指向本地 `127.0.0.1:54321` 或独立 dev 项目）与 `.env.production`（指向正式云端项目），`.env` 只保留真正通用的非敏感项（如 `VITE_PORT`）；其二，后端同样为 dev/prod 准备独立的 Supabase URL 与密钥文件，prod 的 service_role 密钥绝不出服务端、绝不进前端。这样开发/测试不会再触碰生产云端 Auth，本地 SQLite 与云端 Supabase 两个数据源物理分离。

## 综合分析

两层隔离要解决的是两类不同的「污染」：mock 服务解决「前端请求污染本地/真实数据库」，Supabase 环境隔离解决「Auth 调用污染云端用户表」。二者必须配合——只做 mock 而 Supabase 仍共用，测试注册依旧写云端；只换 Supabase 环境而前端仍直连真实后端，则数据库仍可能被测试数据弄脏。推荐的落地顺序是先修环境变量隔离（成本最低、立刻见效），再用 MSW/Mockoon 做前端 mock，最后为需要真实 Auth 行为的集成测试起本地 Supabase 栈。免费路径完整可行：MSW、Mockoon、Prism、json-server 均为开源免费，Supabase 本地栈与 1 个免费云端项目合计零成本。

## 结论

(a) 可以实现，手段是「前端 mock 工具（MSW/Mockoon/Prism 等）+ Supabase 环境隔离（本地栈或独立 dev 项目）+ 环境变量切换」三层组合。(b) 免费推荐：MSW、Mockoon、json-server、Prism、Mirage JS、WireMock OSS（均为开源免费），云端可选 Beeceptor（50 请求/天免费）或 Mocky（完全免费）；Supabase 本地 Docker 栈免费且零云端成本，正式项目用 1 个 Free tier 即可。(c) 这类 mock 服务不仅存在，而且生态成熟、主流工具都在维护。优先行动项：先把当前混用的同一 Supabase 项目按环境拆分，再用 MSW 在开发/测试启用前端 mock。

## 局限

部分官方定价页未披露精确数字（如 Postman mock 调用次数上限、Mockoon Cloud 外的具体档位），已在正文标注「需核实」。json-server 1.x 仍处 beta，生产关键场景建议锁 v0.17。本仓库 `.env` 现状系基于调研时读取的前端配置文件，落地前建议团队再次核对 `.env.production`/`.env.staging` 是否确实需要补 Supabase 配置（生产若本就走 Supabase，则必须显式写入而非依赖 `.env` 兜底）。微信文章检索在中文长关键词下受 Windows 控制台编码限制，部分中文查询以 ASCII 关键词补全，结论已用可访问的微信原文与官方文档交叉验证。

## 参考资料

1. [Mockoon 官网](https://mockoon.com/)
2. [json-server GitHub](https://github.com/typicode/json-server)
3. [Prism (Stoplight) GitHub](https://github.com/stoplightio/prism)
4. [MSW 官方文档](https://mswjs.io/docs/comparison)
5. [Mirage JS 官网](https://miragejs.com/)
6. [WireMock 官网](https://wiremock.org/)
7. [Beeceptor 定价](https://beeceptor.com/pricing/)
8. [Mocky 官网](https://mockyapi.org/en)
9. [Apifox 官网](https://www.apifox.cn/)
10. [Supabase 定价](https://supabase.com/pricing)
11. [Supabase 本地开发文档](https://supabase.com/docs/guides/local-development)
12. [Supabase JWT 文档](https://supabase.com/docs/guides/auth/jwts)
13. [Vite 环境变量与模式（官方中文）](https://cn.vitejs.dev/guide/env-and-mode)
14. [前端 Mock 数据方案，我是如何选择的？｜公众号：前端工匠](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgSxpIjTLo2YfLYXV2isVTPHk7pTRsRbSELVqXa8Fplpd9ayj6hc0aDi_PJa25BYlAARZDBs9fMX2p3KQIIhFIfPkx_9JF2GSezCWr7XrJ4kiDBgAFbfMTwFVj_J3gO0hAik-bAGM9mHkYgy09SJicdIAGJgSR_9YeT_fxgR8mpukGCj4PQVFFBdplnDb5ibF8eDxeZbtj4uJiVEHnbqeAxxiAFV_3u-a3OQ..&type=2&query=API%20mock%20service%20frontend&token=50D92B9965C495C5B1B7E99A73C351B1B17D2CAF6A81C74E) （2023-11-20）
15. [Serverless 数据库三剑客 Supabase vs Neon vs Turso｜公众号：良辰美](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgSxpIjTLo2YfL0CK1hIEYorA7pTRsRbSELVqXa8Fplpd9SfcQCoTtXd0mhztD3p6YsF15pkFOb1PO_sBBh_1LaY1YWy12G-ScmBJEcTBiWoBHWyfvhXwQuxHohpGYzpTYNb8jCTNdVScfEbmAs24t81RujVygztRCPj6CsexRUZVPAA626u6OIV_NQfvmrD74RTaszIwHZ6mI1EmEe2z72dvdrgozfSg6bw..&type=2&query=Supabase%20local%20development&token=50D939F548EABAEB9D9BC4B75D093E3D9EA570636A81C751) （2026-01-31）
16. [用上这款 MOCK 神器，写前端代码再也不用看后端脸色了｜公众号：戈城](https://mp.weixin.qq.com/s?__biz=MzA5MzI3NjE2MA==&mid=2650263602&idx=1&sn=1b81000f04628c63d790b6a83a7eb321)
17. [还在苦苦等后端接口？这 4 种 MOCK 方案让你开发效率翻倍！｜CSDN](https://blog.csdn.net/razyliang/article/details/151814586)
