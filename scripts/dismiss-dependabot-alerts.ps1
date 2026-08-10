# 批量 dismiss fundmate 仓库的 Dependabot alert（基于已删除 manifest 的残留 + dev 工具链不可达）
# 前置：需 gh 已登录且具备 security_events / admin:repo_hook 权限
#   若提示权限不足，先在本机浏览器环境跑： gh auth refresh -h github.com -s admin:repo_hook
# 用法： .\scripts\dismiss-dependabot-alerts.ps1

$ErrorActionPreference = 'Continue'
$repo = 'imoyao/fundmate'

# 拉全部 open alert 编号
$json = gh api --paginate "repos/$repo/dependabot/alerts" 2>$null | ConvertFrom-Json
$open = $json | Where-Object { $_.state -eq 'open' }
$ids = $open | ForEach-Object { $_.number }
Write-Host "open alerts: $($ids.Count)"

# 写 body 到临时文件，避免 PowerShell 管道 BOM 导致 JSON 解析失败
$bodyPath = Join-Path $env:TEMP 'dismiss_body.json'
Set-Content -Path $bodyPath -Value '{"dismissed_reason":"not_used"}' -Encoding ASCII

$ok = 0; $fail = 0; $fails = @()
foreach ($id in $ids) {
    $r = gh api -X PATCH "repos/$repo/dependabot/alerts/$id" --input $bodyPath 2>&1
    if ($LASTEXITCODE -eq 0) { $ok++ } else { $fail++; $fails += "$id`: $r" }
}
Write-Host "dismissed ok: $ok / fail: $fail"
if ($fails.Count -gt 0) { $fails | Out-File -Encoding utf8 da_dismiss_fail.txt; Write-Host "fails saved to da_dismiss_fail.txt" }
