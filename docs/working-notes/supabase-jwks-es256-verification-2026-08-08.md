# Supabase JWT 验签改造：JWKS + ES256（2026-08-08）

> 配套决策：`docs/spec/decisions.md` D2 修订（2026-08-08「JWT 验签改为 JWKS+ES256」）。
> 本文记录实证过程与三条关键教训，防止后续写代码时再次踩坑。

## 背景

`app/core/auth.py` 的 `decode_supabase_token` 用 HS256 + `SUPABASE_JWT_SECRET` 验签，
但日志持续报 `Supabase token 验签失败`。先怀疑密钥不对，实测后确认是**算法级迁移**：

- Dashboard「JWT Signing Keys」：Current key `ae2a6752-…` 与 Standby key `ad1cd269-…` 均为 **ECC (P-256)**；
  Previous key `d0fd7dd6-…` 才是 **Legacy HS256**，且约 2 个月前已轮换。
- `.env` 里的 `SUPABASE_JWT_SECRET=ae2a6752-e497-4e0f-bd27-aef31f22b0aa` 是 **Current key 的 Key ID（UUID），不是密钥材料**。
  把 UUID 当 HS256 secret 用，必然验签失败——不是"换对了 secret"能修好的，必须换验签方案。

## 实证结果（file:line 级）

1. **JWKS 真实路径**：OpenID Discovery
   `GET https://owhbssypqaghpnjoxlkx.supabase.co/auth/v1/.well-known/openid-configuration`
   返回 `jwks_uri = https://owhbssypqaghpnjoxlkx.supabase.co/auth/v1/.well-known/jwks.json`。
   **臆造的 `/auth/v1/jwks` 返回 404**，勿用。
2. **端点要求 `apikey` 头**：不带头访问返回
   `{"message":"No API key found in request","hint":"No`apikey`request header or url param was found."}`。
   实测带 `apikey` + `Authorization: Bearer <anon_key>` 即 200。
3. **JWKS 内容**（2 条公钥，均为 ES256 / P-256）：
   - `kid=ae2a6752-e497-4e0f-bd27-aef31f22b0aa`（对应 Dashboard Current key）
   - `kid=ad1cd269-820e-4394-8788-24dd32159508`（对应 Standby key）
   - token header 的 `kid` 决定用哪把公钥验签 → 天然支持密钥轮换（Current 失效自动切 Standby）。
4. **PyJWT 验签**：`jwt.algorithms.ECAlgorithm.from_jwk(jwk)` 可直接由 JWK 构造公钥对象，
   `jwt.decode(token, pubkey, algorithms=['ES256'], audience='authenticated')` 验签通过。
   本机 PyJWT 2.13.0 / cryptography 50.0.0 均可用。

## 改动

- `backend/app/core/auth.py`：
  - 新增 `_fetch_jwks()`（用 `SUPABASE_ANON_KEY` 做 apikey 头，拉 `.well-known/jwks.json`）；
  - 新增 `_get_public_key()` + 模块级 `_JWKS_CACHE`（按 kid 缓存公钥，TTL 1h，带锁防并发重复拉取）；
  - `decode_supabase_token()` 改为：解析 header 取 `kid` → 查/拉公钥 → `ES256` 验签；
  - 删除对 `SUPABASE_JWT_SECRET` 的依赖。
- `backend/.env`：移除 `SUPABASE_JWT_SECRET` 行（无效且已废弃）。
- `backend/tests/test_auth.py`：新增 `supabase_jwks` fixture——内存生成 P-256 密钥对、
  mock 掉 `_fetch_jwks`、ES256 签发 token，5 个涉 JWT 用例全部改用它（与原 HS256 用例一一对应）。
- `docs/spec/decisions.md`：追加 D2 修订决策条目。
- `docs/backend-restructure-edgeone-dualengine.md`：env 清单标注 `SUPABASE_JWT_SECRET` 废弃。

## 验证

- `pdm run python -m pytest -p no:xdist tests/test_auth.py -q` → **33 passed**。
- 密钥算法冒烟：内存 ES256 签发 + `ECAlgorithm.from_jwk` 验签通过（与测试 fixture 同链路）。

## 教训（下次写代码前先看这里）

1. **Supabase `SUPABASE_JWT_SECRET` 形如 UUID 时，几乎可以断定它是 Key ID 而非密钥**。
   先到 Dashboard → Project Settings → API → JWT Signing Keys 核对 Key 类型：
   - HS256（Legacy）→ 才有共享 secret 可做 HS256 验签；
   - ECC (P-256)（Current/Standby）→ 必须走 **JWKS 非对称验签（ES256）**，不存在可用的"共享密钥"。
2. **JWKS 端点路径以 OpenID Discovery 的 `jwks_uri` 为准**，不要臆造：
   `GET {SUPABASE_URL}/auth/v1/.well-known/openid-configuration` 返回的 `jwks_uri` 才是正解
   （本项目是 `/auth/v1/.well-known/jwks.json`；`/auth/v1/jwks` 会 404）。
3. **Supabase 的 JWKS 端点要 `apikey` 头**（用 `SUPABASE_ANON_KEY`），否则 401
   `"No API key found in request"`。这与其他公开 JWKS 端点（如 GitHub/Google）不同，别想当然。
4. 写测试时**不要再用 HS256 假 token**：本地用 `cryptography` 生成 P-256 密钥对、
   ES256 签发、mock `_fetch_jwks`，与生产验签链路完全一致，才能守住"有效 token 通过/伪造 token 拒绝"。
