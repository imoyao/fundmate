# syntax=docker/dockerfile:1
# =============================================================================
# 多倍贝后端镜像（V2，app/ 域分包架构）
#
# 2026-10-17 重写。旧 Dockerfile 是 V1 时代的遗留，自 2026-08-01 V1 退役后从未
# 构建成功过：引用的 requirements/prod.txt、package.json、webpack.config.js、
# autoapp.py、fundmate/、assets/ 全部不存在；基础镜像 python:3.7 / node:12（buster）
# 均已 EOL；supervisord 的 CMD 与 COPY 目标路径互不匹配。历史登记见
# docs/working-notes/launch-plan-2026-08-09.md 与 mvp-launch-blockers-2026-08-18.md。
#
# 构建 / 运行：
#   docker build -t fundmate-backend backend/
#   docker run --rm -p 8000:8000 \
#     -e APP_ENV=development \
#     -e DEV_DATABASE_URL=sqlite:////app/data/invest.db \
#     -e DATABASE_URL=sqlite:////app/data/invest.db \
#     -v fundmate-data:/app/data fundmate-backend
#
# 要点：
# - 依赖严格取自 pdm.lock（pdm sync，不触发重锁）。pdm export 在本仓锁文件上被
#   PdmUsageError 拒绝（缺 environment markers），故弃 export 用 sync。
# - gunicorn 不在 pyproject 依赖里（本地 Windows 开发用不到，且其不支持 Windows），
#   仅在镜像内钉版本补装——本 Dockerfile 是 gunicorn 版本的唯一声明处。
# - gunicorn 必须单 worker：create_app() 内的 instance_guard（#1809）持进程级 OS
#   排他锁、冲突即退出码 4，而 gunicorn 默认每个 worker 各自 create_app()，多
#   worker 会互相踩锁进入崩溃循环；SQLite 单写者语义下「1 worker + 多线程」也是
#   正确形态（见 CMD 注释）。
# - Playwright 只装 Python 包、不装浏览器：温度计韭圈儿的 Playwright 降级路径
#   捕获全部异常并优雅降级（app/services/thermometer/fetchers.py:375-377）。
#   需要浏览器时在 production 段补 `playwright install --with-deps chromium`。
# =============================================================================

ARG PYTHON_VERSION=3.12

# ------------------------------ 依赖构建层 ----------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PDM_CHECK_UPDATE=false \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir "pdm>=2.26,<3"

# 先只拷依赖声明，让「依赖不变则本层缓存命中」
COPY pyproject.toml pdm.lock ./

# -d/--prod 排除 dev 依赖组；--no-self 不构建项目自身（运行段以 /app 源码直跑，
# 无需 wheel 化）；--no-editable 兜底。PDM 默认在项目内建 .venv——与运行段同路径
# （/app/.venv），因此脚本 shebang 在复制后依然有效。
RUN pdm sync -d --no-editable --no-self

# 补装 WSGI 服务器（钉版本，来源仅此一处；版本已核对 pip 索引存在）
RUN /app/.venv/bin/python -m pip install --no-cache-dir gunicorn==26.2.0

# ------------------------------ 运行镜像 ------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PATH="/app/.venv/bin:$PATH"

# tzdata：TZ=Asia/Shanghai 的系统时区兜底（slim 基础镜像不带 zoneinfo 数据时
# time.tzset / 按系统时区换算的第三方库需要它）
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 非 root 运行；/app/data 与 /app/logs 是仅有的运行期可写落点（实例锁
# data/app_instance.lock、缓存、快照、可选文件日志），挂卷时也挂这里。
# 注意：数据文件（invest.db 等）默认不进镜像，由 DATABASE_URL 系环境变量
# 指到挂卷路径，见 docker-compose.yml。
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data /app/logs \
    && chown -R app:app /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app . /app

USER app

EXPOSE 8000

# 单 worker 是硬约束（见文件头注释：instance_guard 进程锁 + SQLite 单写者）；
# 并发靠 gthread 多线程（GunicornThreads）。SCHEDULER_ENABLED 默认关，
# 若要常驻调度：另跑一个 `python app/tools/scheduler_daemon.py` 进程/容器，
# 不要在本进程开（避免随 worker 生命周期漂移）。
# 首次请求前 worker 需 import akshare/scipy 等重依赖，start-period 给足 30s。
# shell 形式 + exec：exec 让 gunicorn 顶替 sh 成为 PID 1，SIGTERM 直达、可优雅退出
CMD exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --worker-class gthread \
    --threads "${GUNICORN_THREADS:-8}" \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    app.main:app

# /api/health 是免登录白名单端点（app/domains/health.py），返回 200 即存活；
# 数据库/调度异常会在 JSON 里报 degraded，但不影响探活语义（本探针只看连通）。
HEALTHCHECK --interval=60s --timeout=6s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
