# 身份类事件审计台账（auth_audit）

> 决策依据：`docs/spec/decisions.md` **D76**；来源 **#2780**。
> 本文是**生产执行清单**，不是设计草案——照着做，做不完的部分在文末「未完成项」里明列。

## 1. 为什么是「观察者」而不是收口

改邮箱走的是前端直连 GoTrue（`supabase.auth.updateUser({ email })`），GoTrue 会发确认邮件、
要求邮箱双确认、并通知旧邮箱。**这三件事都正常，不需要救。**

缺的只有一格：后端完全不知道邮箱变更发生过。而用 Admin API 把写入收口到后端，代价是
**制造第二条写入路径**（此后邮箱可能被 Admin API 和 GoTrue 各改一次）。所以本方案：

- **写入路径一个字都不动**；
- 只在数据库层挂一个观察者，把变更记到 `auth_audit`。

`auth_audit` 在 **user 域**（`app/core/db_factory.py` 的 `DATA_DOMAIN_REGISTRY`），
与 `auth.users` 同库，触发器才能直接写。

## 2. 两个写入方（刻意不合并）

| `source` | 谁写 | 覆盖什么 | 本地能否验证 |
|---|---|---|---|
| `supabase` | `auth.users` 的 `AFTER UPDATE` 触发器 | **邮箱 / 密码 / 手机号变更**（本仓后端看不见的那半） | ❌ 本地无 `auth.users` |
| `backend` | 本仓认证端点请求流水 | resolve 命中/未命中/被限流、logout、资料变更 | ✅ pytest |

## 3. 执行顺序（三步，别倒过来）

表**不由人手写 DDL** —— 它由后端 `init_db()` 的 `user_meta.create_all(bind=user_eng)` 建出，
模型是唯一真源（`backend/app/domains/users/models.py::AuthAuditLog`）。手写 DDL 会与模型漂移，
随后被启动时的 `_validate_schema` 判红。

1. **先部署后端**（含本 PR），确认 Supabase 侧已出现 `public.auth_audit` 表：
   ```sql
   SELECT column_name, data_type, is_nullable
   FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'auth_audit'
   ORDER BY ordinal_position;
   ```
   预期 11 列：`user_id` / `supabase_id` / `event` / `source` / `identifier` / `ip` /
   `user_agent` / `detail` / `id` / `created_at` / `updated_at`。

2. **锁死曝光面**（**必做，不是可选**）。`public` schema 会经 PostgREST 暴露给 anon key，
   这张表里是 IP / UA / 邮箱，默认权限等于把它们公开：
   ```sql
   ALTER TABLE public.auth_audit ENABLE ROW LEVEL SECURITY;
   REVOKE ALL ON public.auth_audit FROM anon, authenticated;
   -- 不建任何 policy：除 service_role / 直连 postgres 外一律不可读
   ```

3. **建触发器**（幂等，可重复执行）：
   ```sql
   CREATE OR REPLACE FUNCTION public.record_auth_user_change() RETURNS trigger
   LANGUAGE plpgsql
   SECURITY DEFINER
   SET search_path = ''
   AS $$
   DECLARE
     v_event  text;
     v_detail jsonb;
   BEGIN
     IF NEW.email IS DISTINCT FROM OLD.email THEN
       v_event := 'auth.email.changed';
       v_detail := jsonb_build_object(
         'old', OLD.email, 'new', NEW.email,
         'old_confirmed_at', OLD.email_confirmed_at,
         'new_confirmed_at', NEW.email_confirmed_at
       );
     ELSIF NEW.encrypted_password IS DISTINCT FROM OLD.encrypted_password THEN
       v_event := 'auth.password.changed';
       v_detail := jsonb_build_object('changed_at', now());
     ELSIF NEW.phone IS DISTINCT FROM OLD.phone THEN
       v_event := 'auth.phone.changed';
       v_detail := jsonb_build_object('old', OLD.phone, 'new', NEW.phone);
     ELSE
       RETURN NEW;   -- 与身份无关的 UPDATE（登录时间等）不记，避免台账被刷爆
     END IF;

     INSERT INTO public.auth_audit (supabase_id, event, source, detail, created_at, updated_at)
     VALUES (
       NEW.id::text, v_event, 'supabase', v_detail::text,
       now() AT TIME ZONE 'Asia/Shanghai', now() AT TIME ZONE 'Asia/Shanghai'
     );

     RETURN NEW;
   EXCEPTION WHEN OTHERS THEN
     -- 记账失败绝不阻断认证（D76 裁决二）：只发 WARNING，让 UPDATE 照常提交
     RAISE WARNING '[auth_audit] 写入失败（已忽略）：% / %', v_event, SQLERRM;
     RETURN NEW;
   END;
   $$;

   CREATE TRIGGER trg_auth_users_audit
     AFTER UPDATE ON auth.users
     FOR EACH ROW
     EXECUTE FUNCTION public.record_auth_user_change();
   ```

## 4. 上线前必须先查的一件事（否则台账会骗人）

GoTrue 的「安全邮箱变更」不保证**立刻**改 `email` 列：多数版本会把待确认地址写进另一个
待确认列，确认后才 swap，`email` 在此期间保持不变。**只判 `email` 就会漏掉「发起变更」
这个时刻**——而那正是「账号什么时候被盯上」的关键证据。

执行前先看表结构：

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'auth' AND table_name = 'users'
  AND (column_name LIKE '%email_change%' OR column_name LIKE '%email%' OR column_name LIKE '%token%');
```

- 若存在 `email_change`（或同类待确认列），把上面的判定分支**改成同时覆盖它**，
  事件名记 `auth.email.change_requested`（发起）与 `auth.email.changed`（完成）两条；
- 若不存在，说明该版本直接改 `email`，现有 DDL 即可。

不要跳过这一步：跳过就等于把「发起变更」这一格又空着了。

## 5. 核验（出事后查什么）

```sql
-- 某个用户最近 90 天的身份变更（user_id 从 users.supabase_id 拿）
SELECT created_at, source, event, detail
FROM public.auth_audit
WHERE supabase_id = '<supabase uuid>'
  AND created_at >= now() - interval '90 days'
ORDER BY created_at DESC;

-- 全站近 30 天换过邮箱的账号（排查批量接管）
SELECT created_at, supabase_id, detail ->> 'old' AS old_email, detail ->> 'new' AS new_email
FROM public.auth_audit
WHERE event LIKE 'auth.email.change%'
  AND created_at >= now() - interval '30 days'
ORDER BY created_at DESC;
```

## 6. 回滚

```sql
DROP TRIGGER IF EXISTS trg_auth_users_audit ON auth.users;
DROP FUNCTION IF EXISTS public.record_auth_user_change();
```

触发器删掉即恢复原状，**表保留**（历史留证比「干净」重要）。表本身的回滚由 revert PR 后的
`DROP TABLE public.auth_audit` 完成。

## 7. 未完成项（本文件当前只覆盖到触发器）

- [ ] 后端认证端点请求流水（`source='backend'`）：落点必须是**请求后置钩子**，
      `auth/views.py` 已顶满视图厚度基线（113 行 / max_func 28），在视图里加行即判红。
- [ ] 台账保留期与脱敏口径（IP 截断粒度、UA 截断长度、保留天数）——现在只写了「必须脱敏」，
      具体数值待定，别默认永久存原文。
- [ ] 一条面向运维的只读入口（脚本或接口），目前只能手写 SQL。
