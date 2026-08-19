#!/usr/bin/env node
/**
 * 极谷（jigu）跨 Supabase project 数据迁移脚本
 * ---------------------------------------------------------------
 * 旧站 jigu.masantu.com (旧 project)  ->  主站 project (app/jigu.duoduobei.com 共用)
 *
 * 策略（见 docs/working-notes/jigu-migration-to-duoduobei-plan-2026-08-18.md）：
 *   - 仅做“字节级拷贝”：把 user_configs.data (JSON) 原样搬到主 project。
 *   - 不做任何字段解析 / 精度转换（那是阶段二 structured 入 fundmate 表要做的）。
 *   - 按 email 映射 user_id：旧 project 的 user_id -> 主 project 同邮箱用户的 user_id。
 *   - 幂等 upsert：可重复跑，不覆盖非迁移写入。
 *
 * 安全性：
 *   - 仅用 service_role key（服务端，绕过 RLS）。绝不可在前端/仓库出现。
 *   - 默认 DRY-RUN（只打印计划、不写库）。必须显式 --apply 才真正写入。
 *
 * 用法：
 *   cd backend/scripts/jigu_migration
 *   npm install @supabase/supabase-js dotenv
 *   cp .env.example .env        # 填入 4 个变量
 *   node migrate_jigu_users.js            # 先 dry-run 看计划
 *   node migrate_jigu_users.js --apply    # 确认无误后正式迁移
 */

require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');

// ---------------------------------------------------------------------------
// 配置（从 .env 读取；不要硬编码 key）
// ---------------------------------------------------------------------------
const OLD_URL = process.env.OLD_SUPABASE_URL;
const OLD_SVC = process.env.OLD_SUPABASE_SERVICE_ROLE_KEY;
const NEW_URL = process.env.NEW_SUPABASE_URL;
const NEW_SVC = process.env.NEW_SUPABASE_SERVICE_ROLE_KEY;

const APPLY = process.argv.includes('--apply') || process.env.APPLY === 'true';
const PER_PAGE = 200;

function fail(msg) {
  console.error(`[ERROR] ${msg}`);
  process.exit(1);
}

[['OLD_SUPABASE_URL', OLD_URL], ['OLD_SUPABASE_SERVICE_ROLE_KEY', OLD_SVC],
 ['NEW_SUPABASE_URL', NEW_URL], ['NEW_SUPABASE_SERVICE_ROLE_KEY', NEW_SVC]]
  .forEach(([name, val]) => { if (!val) fail(`缺少环境变量 ${name}`); });

const oldSb = createClient(OLD_URL, OLD_SVC, { auth: { autoRefreshToken: false, persistSession: false } });
const newSb = createClient(NEW_URL, NEW_SVC, { auth: { autoRefreshToken: false, persistSession: false } });

// ---------------------------------------------------------------------------
// 工具：分页枚举全部 auth.users（含 email）
// ---------------------------------------------------------------------------
async function listAllUsers(supabase, label) {
  const users = [];
  let page = 1;
  while (true) {
    const { data, error } = await supabase.auth.admin.listUsers({ page, perPage: PER_PAGE });
    if (error) fail(`列举 ${label} 用户失败: ${error.message}`);
    users.push(...data.users);
    if (data.users.length < PER_PAGE) break;
    page += 1;
  }
  return users;
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
async function main() {
  console.log(`模式: ${APPLY ? 'APPLY (真实写入)' : 'DRY-RUN (只打印计划)'}`);

  const oldUsers = await listAllUsers(oldSb, '旧');
  const newUsers = await listAllUsers(newSb, '新');

  const oldById = new Map(oldUsers.map((u) => [u.id, u]));
  const newByEmail = new Map(
    newUsers.filter((u) => u.email).map((u) => [u.email.toLowerCase(), u])
  );

  console.log(`旧 project 用户数: ${oldUsers.length}；新 project 用户数: ${newUsers.length}`);

  // 读取旧 project 全部 user_configs
  const { data: oldConfigs, error: cfgErr } = await oldSb
    .from('user_configs')
    .select('user_id, data, updated_at, last_device_id, ytd_return_rate');
  if (cfgErr) fail(`读取旧 user_configs 失败: ${cfgErr.message}`);
  console.log(`旧 user_configs 行数: ${oldConfigs.length}`);

  const plan = []; // { email, oldUserId, newUserId|null, action }
  const needCreate = [];

  for (const cfg of oldConfigs) {
    const oldUser = oldById.get(cfg.user_id);
    const email = oldUser?.email?.toLowerCase();
    if (!email) {
      console.warn(`  [跳过] user_configs(${cfg.user_id}) 找不到对应 email，可能用户已删`);
      continue;
    }
    const existing = newByEmail.get(email);
    if (existing) {
      plan.push({ email, oldUserId: cfg.user_id, newUserId: existing.id, action: 'upsert', cfg });
    } else {
      plan.push({ email, oldUserId: cfg.user_id, newUserId: null, action: 'create+upsert', cfg });
      needCreate.push(email);
    }
  }

  console.log('\n==== 迁移计划 ====');
  console.log(`直接 upsert（新站已存在该邮箱）: ${plan.filter((p) => p.action === 'upsert').length}`);
  console.log(`需先建号再 upsert（新站尚无该邮箱）: ${needCreate.length}`);
  if (needCreate.length) console.log(`  待建号邮箱: ${needCreate.join(', ')}`);

  if (!APPLY) {
    console.log('\n[DRY-RUN] 未做任何写入。确认无误后运行: node migrate_jigu_users.js --apply');
    return;
  }

  // ---- 正式写入 ----
  let created = 0;
  let upserted = 0;
  for (const p of plan) {
    let newUserId = p.newUserId;
    if (!newUserId) {
      // 在主 project 建号（passwordless，用户用魔法链接登录，不强制设密码）
      const { data: cu, error: ce } = await newSb.auth.admin.createUser({
        email: p.email,
        email_confirm: true,
        user_metadata: { source: 'jigu_migration' },
      });
      if (ce) { console.error(`  [失败] 建号 ${p.email}: ${ce.message}`); continue; }
      newUserId = cu.user.id;
      newByEmail.set(p.email, cu.user);
      created += 1;
    }
    const { error: ue } = await newSb
      .from('user_configs')
      .upsert(
        {
          user_id: newUserId,
          data: p.cfg.data,
          updated_at: p.cfg.updated_at,
          last_device_id: p.cfg.last_device_id,
          ytd_return_rate: p.cfg.ytd_return_rate,
        },
        { onConflict: 'user_id' }
      );
    if (ue) { console.error(`  [失败] upsert ${p.email}: ${ue.message}`); continue; }
    upserted += 1;
  }

  // ---- 校验：新 project 行数 ---
  const { count, error: cntErr } = await newSb
    .from('user_configs')
    .select('*', { count: 'exact', head: true });
  if (!cntErr) {
    console.log(`\n==== 完成 ====\n新建账号: ${created}；upsert 成功: ${upserted}；新 project user_configs 总行数: ${count}`);
  }
}

main().catch((e) => fail(e.stack || String(e)));
