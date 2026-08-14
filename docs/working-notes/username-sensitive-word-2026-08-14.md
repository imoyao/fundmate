# 用户名 / 昵称敏感词校验（2026-08-14）

> 触发：用户指出 `python-usernames` 对中文支持弱（纯英文黑名单、精确匹配、无拼音/谐音），不适合中文场景；要求编辑用户名/昵称时加敏感词校验。本文件固化现状、库选型事实、推荐方案与排期。
> 范围：评估 + 方案固化 + 拆 Issue；**不动业务代码**。

---

## 1. 现状盘点（代码事实）

- 后端 `app/domains/users/schemas.py`：`ProfileUpdate` 已对 `username`(5-20) / `nickname`(5-16) 做长度校验，并用 `field_validator('username','nickname', mode='before')` 先 `strip` 防绕过。**但完全没有敏感词/脏话校验**。
- 后端 `app/domains/users/views.py`：`PATCH /api/users/me` 对 `username` 做唯一性冲突校验（409），对 `nickname` 直接赋值。**不过滤敏感词**。
- 前端 `views/profile/index.vue`（Vue 3 + Element Plus）：`onSaveUsername` / `onSaveNickname` 已有 `trim` + 长度校验，调 `updateMe`。**无前端敏感词提示**。
- `pyproject.toml`：**未引入任何敏感词库**（无 `python-usernames` / `sensitive-word-filter-cn` 等）。

结论：敏感词校验在当前代码中**完全缺失**，需从零加。

---

## 2. 库选型事实纠正（重要）

用户推荐 `sensitive-word-filter-cn`（GitHub: PerryLink/Sensitive-Word-Filter-CN，支持 DFA、拼音/符号/繁简变体）。**核实结果：该库未发布到 PyPI**（PyPI 查 `sensitive-word-filter-cn` → 404），无法 `pdm add` 安装，只能从 GitHub 源码装（供应链风险高、无版本锁、维护依赖上游）。

PyPI 上真实可装的中文敏感词库举例：`ErisPulse-DFAFilter`（2026-02 更新，自带词库 + 持久化 + 自定义词），但质量/自带词库对口度需实测验证；`sensitive` 等常见名在 PyPI 也不存在。

> 原则：fundmate 一贯自研轻量、不堆外部依赖（参考 guards / ocr_service 均自研）。对"单条用户名/昵称"这种低频、小文本场景，**引入维护不明的第三方敏感词库收益有限、风险偏高**。

---

## 3. 推荐方案

### 3.1 后端（核心，必须）

- **优先评估**：`ErisPulse-DFAFilter`（PyPI 可装、自带词库）。实测其 API 与自带词库是否对口（我们只需基础辱骂/色情类，不需要政治类大词库）。
- **备选自研**（更稳）：维护一份小型中文敏感词表（`backend/app/services/sensitive_words.txt` 或 JSON），用轻量 DFA / Aho-Corasick 实现检测（约 30-50 行），**零外部依赖、可审计、可控**。词表按需补充谐音/拼音变体（如 `shagua`、`傻*瓜`）。
- 检测点：在 `ProfileUpdate` 新增 `field_validator`，对 `username` / `nickname` 调 `check_sensitive(value)`，命中则抛 `400`（描述"包含不被允许的词汇"）。复用现有 Pydantic validator 结构，与 strip 同层。
- 范围：`username` + `nickname` 两类编辑字段都覆盖（昵称是展示名，更易被滥用）。注册路径（email 前缀推导的 username）通常为英文、风险低，可后续纳入，不阻塞本期。

### 3.2 前端（辅助，提升 UX，非强制）

- 在 `profile/index.vue` 用 `computed` 对 `profileForm.username` / `profileForm.nickname` 实时提示"含敏感词"；保存前若命中则禁用保存或弹警告。
- 词表与后端同源（同一份 JSON 两份引用，避免漂移），不强制引入 `nex-wordfilter`（npm 前端库）；若需更强变体检测再考虑。
- **安全原则（强调）**：前端过滤仅 UX 提示，**最终拦截必须由后端执行**，永不信任前端。

---

## 4. 排期

| 优先级 | 事项 | Issue | 理由 |
|--------|------|-------|------|
| P2 | 用户名/昵称敏感词校验（后端 validator + 轻量词表，前端提示） | #938（见 §5） | 合规增强、非阻断、实现简单；库选型待定（优先评 ErisPulse-DFAFilter，备选自研 DFA） |

> 标 Q2:YELLOW（重要不紧急）：是合规增强而非阻断性 bug，可在有空档时实现；但应在用户量增长前落地。

---

## 5. 新增 Issue 索引

| # | Issue | 标题 | 象限 | 关联 |
|---|-------|------|------|------|
| 1 | #938 | 用户名/昵称敏感词校验：后端 validator + 轻量词表，前端实时提示 | Q2:YELLOW 重要不紧急 | #933（统一提交层，间接） |

（#938 不依赖导入类 Issue；属独立合规增强。body 含库选型事实纠正与方案备选。）
