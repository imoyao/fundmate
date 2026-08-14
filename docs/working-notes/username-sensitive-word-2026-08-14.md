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

> **核实更正（2026-08-14 后续）**：上一版写"该库未发布到 PyPI（404）"是**核实失误**——查 `https://pypi.org/pypi/sensitive-word-filter-cn/json` 返回 404，但这是 PyPI JSON API 路径/包名规范问题导致，并非库未发布。用户实测 `pip install sensitive-word-filter-cn` 可装。**以用户实测为准：该库确已发布 PyPI，可直接 `pdm add sensitive-word-filter-cn` 安装。** 此处留痕，避免后续误判为"不可装而转向自研"。

用户补充的 PyPI 可选库对比：

| 库 | 作者 | 特点 | 评价 |
|----|------|------|------|
| **sensitive-word-filter-cn** | PerryLink | DFA，拼音变体(`shagua`)/符号干扰(`傻*瓜`)/繁简混合，纯中文优化，百万字<100ms | ⭐ 最推荐，最贴合"中文+用户名" |
| safetext | viddexa | 13 语言（含中文），多语言通用，词库广 | 中文专项不如前者 |
| glin-profanity | — | 25+ 语言，模糊匹配+上下文分析，可配置强 | 中文词库质量待验证 |
| ErisPulse-DFAFilter | — | DFA，轻量零依赖，信息较少 | 词库覆盖/维护需自评估 |
| gangajal | — | WebAssembly，跨语言，字典私有 | 架构重，中文变体支持未知 |

> 最终判断（见 §3）：**引入 `sensitive-word-filter-cn`，不自研**。理由见 §3.1。

---

## 3. 推荐方案

### 3.1 后端（核心，必须）—— 结论：引入 sensitive-word-filter-cn，不自研

**为什么引库而非自研**：
- 该库的核心价值（拼音变体 `shagua`、符号干扰 `傻*瓜`、繁简混合）恰是**自研最难做对**的部分。自研 DFA 只解决精确匹配 + 基础变种，谐音/符号插入式绕过需额外归一化层，等于造半成品词法引擎，投入大且质量难保证。用户名场景对抗性强（用户会主动绕过），正是该库主场。
- fundmate "自研轻量"风格适用于**业务逻辑可控**的部分（guards / ocr_service 是我们自己的策略）；敏感词对抗是通用且别人已做好的领域，不属于"必须自己掌握核心"，自研在这里是劣势。
- 该库是**纯算法库、无网络调用、无外部服务依赖**（对比 MinerU 那种要 Token/云 API 的，风险天差地别）；单条用户名/昵称（<20 字）开销零感知。供应链面只有"这个包本身"，功能聚焦、攻击面小。

**依赖治理（硬约束）**：
1. `pdm add sensitive-word-filter-cn`，锁版本进 `pyproject.toml` + `pdm.lock`，**绝不裸 pip**（fundmate 依赖管理铁律）。
2. 实现阶段先实测 `SensitiveWordFilter.contains()` 对用户名典型变体（拼音/符号/繁简）的命中率，按需 `add_words` 补我们的扩展词（辱骂类为主），必要时裁剪自带词库里我们不需要的政治类大词——**引库但词表可控**。
3. 封装为 `backend/app/services/sensitive_word_guard.py`，对外只暴露 `contains_sensitive(text) -> bool`，便于后续换库或加词不影响调用点。

**检测点**：在 `ProfileUpdate` 新增 `field_validator`，对 `username` / `nickname` 调 `check_sensitive(value)`（`contains_sensitive` 命中则抛 `400`，描述"包含不被允许的词汇"）。复用现有 Pydantic validator 结构，与 strip 同层。
**范围**：`username` + `nickname` 两类编辑字段都覆盖（昵称是展示名，更易被滥用）。注册路径（email 前缀推导的 username）通常为英文、风险低，可后续纳入，不阻塞本期。

### 3.2 前端（辅助，提升 UX，非强制）

- 在 `profile/index.vue` 用 `computed` 对 `profileForm.username` / `profileForm.nickname` 实时提示"含敏感词"；保存前若命中则禁用保存或弹警告。
- 轻量方案即可（简单关键词匹配），不强制引入 `nex-wordfilter`（npm 前端库）；若后续要更强变体检测再考虑。
- **安全原则（强调）**：前端过滤仅 UX 提示，**最终拦截必须由后端执行**，永不信任前端。

---

## 4. 排期

| 优先级 | 事项 | Issue | 理由 |
|--------|------|-------|------|
| P2 | 用户名/昵称敏感词校验（引入 sensitive-word-filter-cn，后端 validator 硬拦截 + 前端提示） | #938（见 §5） | 合规增强、非阻断、实现简单；结论：**引入 sensitive-word-filter-cn（PDM 管理），不自研** |

> 标 Q2:YELLOW（重要不紧急）：是合规增强而非阻断性 bug，可在有空档时实现；但应在用户量增长前落地。

---

## 5. 新增 Issue 索引

| # | Issue | 标题 | 象限 | 关联 |
|---|-------|------|------|------|
| 1 | #938 | 用户名/昵称敏感词校验：引入 sensitive-word-filter-cn，后端 validator 硬拦截 + 前端提示 | Q2:YELLOW 重要不紧急 | #933（统一提交层，间接） |

（#938 不依赖导入类 Issue；属独立合规增强。最终结论：引入 sensitive-word-filter-cn（PDM 管理），不自研；含 PyPI 核实失误留痕与库对比。）
