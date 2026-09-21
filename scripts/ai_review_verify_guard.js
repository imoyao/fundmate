/**
 * 深度线路「防假成功」校验（.github/workflows/ai-review.yml 经 actions/github-script 调用）。
 *
 * WHY 抽成单文件（2026-09-17）：workflow 现在最多跑两轮审查——第 1 轮零产出时，
 * 排除该模型重新探测、换一个模型重试第 2 轮，而**每轮结束都要做同一次校验**。
 * 原先这段逻辑内联在 workflow 里，复制两份必然漂移，故抽成单一来源：
 *
 *     const guard = require(`${process.env.GITHUB_WORKSPACE}/scripts/ai_review_verify_guard.js`);
 *     await guard({ github, context, core });
 *
 * 入参（env，由 workflow 每轮注入）：
 *   AI_REVIEW_BEFORE      审查前的评论数快照（steps.pre-check.outputs.count）
 *   AI_REVIEW_SELECTED_OK 本轮探测有没有选中健康模型（steps.probe*.outputs.selected_ok）
 *   AI_REVIEW_ROUND       轮次（1 / 2），仅用于日志措辞
 *
 * 退出语义：产出有效评论 → 正常返回；否则 core.setFailed()。
 *   —— 第 1 轮由 workflow 的 continue-on-error 接住（只触发换模型重试，不终局）；
 *   —— 第 2 轮没有 continue-on-error，失败即 job 红。
 */
module.exports = async function verifyAiReviewComments({ github, context, core }) {
  const pr = context.payload.pull_request.number;
  const { owner, repo } = context.repo;
  const before = Number(process.env.AI_REVIEW_BEFORE);
  const selectedOk = process.env.AI_REVIEW_SELECTED_OK === 'true';
  const round = process.env.AI_REVIEW_ROUND || '1';

  const hasAiTag = (body) =>
    (body || '').includes('#ai-review-inline') || (body || '').includes('#ai-review-summary');
  const listInline = () => github.rest.pulls.listReviewComments({ owner, repo, pull_number: pr });
  const listGeneral = () => github.rest.issues.listComments({ owner, repo, issue_number: pr });
  const countAll = async () =>
    (await listInline()).data.length + (await github.rest.pulls.listReviews({ owner, repo, pull_number: pr })).data.length;

  // ---- 步骤 1：判断本轮是否新增评论（必须用「审查前」的快照做基准）----
  let after = before;
  for (let i = 0; i < 5; i++) {
    after = await countAll();
    if (after > before) break;
    await new Promise(r => setTimeout(r, 5000));
  }
  const hadNew = after > before;

  // ---- 步骤 2：清理「agent 协议信封泄漏」----
  // 2026-09-10 PR #1412 实测：agent 模式下若模型反复返回 TOOL_CALL 却始终不返回 FINAL，
  // 包内 AgentLoopService 的 force_final 兜底会把最后一条 TOOL_CALL 原文当作最终答案
  // （services/agent/loop/service.py：fallback_step 解析成功但 action 非 FINAL 时走
  //  `final_text = fallback_text`），于是评论区长出
  //    {"action": "TOOL_CALL", "command": "git diff --name-only"}
  // 这类用户不可读的内部协议 JSON。此处直接删除，不让协议泄漏到 PR 上。
  const ENVELOPE_RE = /\{\s*"action"\s*:\s*"(?:TOOL_CALL|FINAL)"/;
  let purged = 0;
  for (const c of (await listInline()).data) {
    if (hasAiTag(c.body) && ENVELOPE_RE.test(c.body)) {
      await github.rest.pulls.deleteReviewComment({ owner, repo, comment_id: c.id });
      purged++;
      core.warning(`已删除泄漏 agent 协议信封的 AI 行内评论 ${c.path}:${c.line}`);
    }
  }
  for (const c of (await listGeneral()).data) {
    if (hasAiTag(c.body) && ENVELOPE_RE.test(c.body)) {
      await github.rest.issues.deleteComment({ owner, repo, comment_id: c.id });
      purged++;
      core.warning('已删除泄漏 agent 协议信封的 AI 整体评论');
    }
  }
  if (purged) core.notice(`清理了 ${purged} 条协议泄漏评论（agent 未返回 FINAL 的兜底路径所致）`);

  // ---- 步骤 3：清理后仍在 PR 上的 AI 评论数，作为「本次是否真产出」的判据 ----
  const aiComments = (await listInline()).data.filter(c => hasAiTag(c.body)).length
    + (await listGeneral()).data.filter(c => hasAiTag(c.body)).length;

  // ---- 步骤 4（#1581 行为 a）：统计「生成标记」类幻觉，只计数、不删除、不影响 job 成败 ----
  // 背景：#1395 / #1491 / #1496 / #1575 / #1578 **五次**复发同一类幻觉——模型声称代码里有
  // `# added` 这类「生成过程残留标记」（diff 标注的形态），而该字符串在补丁里根本不存在。
  // #1577 已用真实数据否决方案 B（「字面量是否出现在 diff 中」这条判定轴会**漏** #1496、
  // 且会**误杀** #1491 的一条真意见）；#1581 拍板只做**最窄的一件事**：在 AI 评论上
  // （**inline 与 summary 两条通道都扫**——第 5 次复发恰恰发生在 summary）识别「生成标记」形态
  // 并写进 job summary。**不删评论、不改 job 成败**（行为 a = 零风险）。
  // 已知取舍（写在这里，避免下一个人以为是缺陷）：
  //   ① 计数是**下界**——只认固定标记形态，不含「伪造其它字面量」类幻觉；
  //   ② **会误计**「在讨论该幻觉」的正常评论（例如「本文件没有 `# added` 残留」）——
  //      行为 a 下的代价只是 summary 里多一行；若将来升级到 b/c（附提示 / 删除），
  //      必须先把「是否对代码内容作断言」这层判定补上，否则就退回到方案 B 的误杀问题。
  const MARKER_PATTERNS = [
    /#\s*(?:added|changed|removed|generated)\b/i,
    /\/\/\s*(?:added|changed|removed|generated)\b/i,
    /<!--\s*(?:added|changed|removed|generated)/i,
  ];
  const findMarkers = (body) => MARKER_PATTERNS.flatMap(re => (body || '').match(re) || []);
  // 整段包 try/catch：这是**附加观测**，绝不能让自身的任何异常影响「防假成功」这条主判定
  // （本步骤若抛错，下面 `if (hadNew && aiComments > 0)` 的 return 就走不到，job 会因守卫自身报错而变红）。
  try {
    const markerRows = [];
    const collectMarkers = (comments, kind) => {
      for (const c of comments) {
        if (!hasAiTag(c.body)) continue;
        const hits = findMarkers(c.body);
        if (!hits.length) continue;
        markerRows.push([
          kind,
          kind === 'inline' ? `${c.path}:${c.line || '-'}` : `comment#${c.id}`,
          [...new Set(hits)].join(' / '),
          (c.body || '').replace(/\s+/g, ' ').slice(0, 120),
        ]);
      }
    };
    collectMarkers((await listInline()).data, 'inline');
    collectMarkers((await listGeneral()).data, 'summary');
    if (!markerRows.length) {
      core.info('生成标记幻觉统计（#1581）：本轮 AI 评论中未发现 `# added` 类生成标记');
    } else {
      core.warning(
        `⚠️ 发现 ${markerRows.length} 条 AI 评论疑似「生成标记」类幻觉（如 \`# added\`）。` +
          ' 本步骤只计数、不删除、不影响 job 成败（#1581 行为 a）——' +
          ' 历史 5 次复发同型，见 docs/configs/ai-review-known-false-positives.md §四。' +
          ' 复核要点：这些标记在 diff 里并不存在，**不要照做**。'
      );
      if (core.summary) {
        await core.summary
          .addHeading(`ai-review 生成标记幻觉统计（#1581 行为 a）：${markerRows.length} 条`, 3)
          .addTable([
            [
              { data: '通道', header: true },
              { data: '位置', header: true },
              { data: '命中标记', header: true },
              { data: '正文预览', header: true },
            ],
            ...markerRows,
          ])
          .addRaw('> 说明：只计数、不删除、不影响 job 成败；计数为**下界**，且会误计「正在讨论该幻觉」的评论。\n')
          .write();
      }
    }
  } catch (err) {
    // 观测失败绝不阻断主判定：只留一条告警，然后继续走下面的成功/失败分支。
    core.warning(`生成标记统计（#1581）执行异常，已跳过（不影响本次校验结论）：${err && err.message}`);
  }

  if (hadNew && aiComments > 0) {
    core.info(`第 ${round} 轮深度线路已发布评论，计数 ${before} → ${after}`);
    return;
  }
  if (selectedOk && aiComments > 0) {
    // 2026-09-11 PR #1411 实测：本轮一条评论都没产出，却因为有 22 条**历史** AI 评论
    // 而被判成功——这是假成功的残留缺口（无法区分「去重跳过」与「本轮静默失败」，
    // ai-review v0.76.0 不在 LLM 报错时非零退出，拿不到该信号）。
    // 成功结论保持不变（历史评论尚在使用期内），但必须打出醒目告警，否则它会一直
    // 伪装成"AI 审查通过"，让人误以为模型额度与 agent 都正常。
    core.warning(
      `⚠️ 第 ${round} 轮未新增评论，仅凭 PR 上已有的 ${aiComments} 条历史 AI 评论判为成功。` +
        ' 这可能是「去重跳过」，也可能是本轮静默失败（假成功）——' +
        ' 请在「AI 深度审查」步骤里核对是否存在以下报错：' +
        " Empty LLM output / No JSON array found in LLM output / Empty LLM summary /" +
        ' FileNotFoundError / Agent command blocked by policy / 429 / 额度告警。'
    );
    core.info(
      '提示：要彻底堵住这个缺口，需 ai-review action 自身在 LLM 报错时非零退出；' +
        ' 当前版本（v0.76.0）不提供该信号，见 tech-debt。'
    );
    return;
  }
  // 未新增评论必须再分两种，**不能只看「探测是否选中健康模型」**。
  // 2026-09-10 PR #1412 实测反例：探测 glm-4.7-flash 返回 200（selected_ok=true），
  // 但真正调用时上游 429（智谱 code 1302「账户已达到速率限制」），agent 模式与兜底
  // 直连双双失败、summary 为空被跳过 → 一条评论都没发，旧逻辑却判为成功（假成功）。
  // 之所以会错配：探测只发一次极短请求，而真实审查是长上下文 + 多轮 agent，
  // 触发限流的概率完全不同 —— 「探测通过」不能等价于「本次审查成功」。
  // 另：若本次只产出了「协议泄漏评论」且已被步骤 2 全部删除，aiComments 会归零，
  // 同样落到这里判失败（本次确实没有面向用户的有效产出）。
  //
  // 残留缺口（已知，不装作没有）：若历史 AI 评论已存在、而本轮又静默失败，仍会放行。
  // 要彻底堵住需要 action 自身在 LLM 报错时非零退出，当前版本（v0.76.0）不提供该信号。
  core.setFailed(
    `第 ${round} 轮深度线路 AI 审查未产出任何有效评论（候选模型均不可用/限流/欠费，模型输出为空，`
    + '或只产出了被清理的协议泄漏评论）——'
    + `selected_ok=${selectedOk}，清理后 PR 上 AI 评论数=${aiComments}，本轮新增=${hadNew}，`
    + `协议泄漏已清理=${purged}。标记为失败以避免假成功；请检查探测步骤输出中的 429 / 额度告警。`
  );
};
