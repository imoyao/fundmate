# FMP

a web app to manage your funds

> ⚠️ **本文为早期脚手架模板留档，所述流程已不适用（#898 核对，2026-10-17）**
>
> 本文成于模板脚手架时期，正文的以下内容**均不反映当前实况**，不要照它操作：
>
> | 文中说法 | 当前实况 |
> |---|---|
> | 标题 `FMP`（及历史包名 `showbuy`） | 产品名为**多多贝**（`showbuy` 仅是 `backend/pyproject.toml` 的历史项目名，见根 `AGENTS.md`） |
> | `flask db init / migrate / upgrade`（flask-migrate / Alembic） | **无迁移链**：建表走 `init_db()` = `Base.metadata.create_all()` + 增量列/索引迁移（`backend/app/core/database.py`），由 `create_app()` 启动时执行（`backend/app/main.py`） |
> | `pip install -r requirements/dev.txt` | 依赖在 `backend/pyproject.toml` + PDM（`pdm install -G dev`），**仓库无 `requirements/` 目录** |
> | `npm install / npm run build`（webpack） | 前端独立于 `frontend/`（Vite + pnpm，见根 `README.md`） |
> | `flask init-db` / `flask test` / `flask lint` | `pdm run pytest -p no:xdist` / `pdm run ruff check .`，日常指令见 `backend/tasks.py`（invoke） |
>
> 当前的安装、启动、同步与测试命令以**仓库根 `README.md`** 与 **`docs/dev/index.md`** 为准。

## Docker Quickstart

This app can be run completely using `Docker` and `docker-compose`. **Using Docker is recommended, as it guarantees the application is run using compatible versions of Python and Node**.

There are three main services:

To run the development version of the app

```bash
docker-compose up flask-dev
```

To run the production version of the app

```bash
docker-compose up flask-prod
```

The list of `environment:` variables in the `docker-compose.yml` file takes precedence over any variables specified in `.env`.

To run any commands using the `Flask CLI`

```bash
docker-compose run --rm manage <<COMMAND>>
```

Therefore, to initialize a database you would run

```bash
docker-compose run --rm manage db init
docker-compose run --rm manage db migrate
docker-compose run --rm manage db upgrade
```

A docker volume `node-modules` is created to store NPM packages and is reused across the dev and prod versions of the application. For the purposes of DB testing with `sqlite`, the file `dev.db` is mounted to all containers. This volume mount should be removed from `docker-compose.yml` if a production DB server is used.

### Running locally

Run the following commands to bootstrap your environment if you are unable to run the application using Docker

```bash
cd fundmate
pip install -r requirements/dev.txt
npm install
npm run-script build
npm start  # run the webpack dev server and flask server using concurrently
```

You will see a pretty welcome screen.

#### Database Initialization (locally)

Once you have installed your DBMS, run the following to create your app's
database tables and perform the initial migration

```bash
# 创建数据库
flask init-db
# 或者
flask db init
# 数据库更新
flask db migrate
flask db upgrade
```

::: danger 数据库升级报错
如果遇到报错 `ERROR [flask_migrate] Error: Can't locate revision identified by 'xxxx'`，可能是分支切换导致的，可以尝试将数据表`alembic_version`删除后重试。
:::

## Deployment

When using Docker, reasonable production defaults are set in `docker-compose.yml`

```text
FLASK_ENV=production
FLASK_DEBUG=0
```

Therefore, starting the app in "production" mode is as simple as

```bash
docker-compose up flask-prod
```

If running without Docker

```bash
export FLASK_ENV=production
export FLASK_DEBUG=0
export DATABASE_URL="<YOUR DATABASE URL>"
npm run build   # build assets with webpack
flask run       # start the flask server
```

## Shell

To open the interactive shell, run

```bash
docker-compose run --rm manage db shell
flask shell # If running locally without Docker
```

By default, you will have access to the flask `app`.

## Running Tests/Linter

To run all tests, run

```bash
docker-compose run --rm manage test
flask test # If running locally without Docker
```

To run the linter, run

```bash
docker-compose run --rm manage lint
flask lint # If running locally without Docker
```

The `lint` command will attempt to fix any linting/style errors in the code. If you only want to know if the code will pass CI and do not wish for the linter to make changes, add the `--check` argument.

## Migrations

Whenever a database migration needs to be made. Run the following commands

```bash
docker-compose run --rm manage db migrate
flask db migrate # If running locally without Docker
```

This will generate a new migration script. Then run

```bash
docker-compose run --rm manage db upgrade
flask db upgrade # If running locally without Docker
```

To apply the migration.

For a full migration command reference, run `docker-compose run --rm manage db --help`.

If you deploy your application remotely (e.g. on Heroku) you should add the `migrations` folder to version control.
You can do this after `flask db migrate` by running the following commands

```bash
git add migrations/*
git commit -m "Add migrations"
```

Make sure folder `migrations/versions` is not empty.

## Asset Management

Files placed inside the `assets` directory and its subdirectories
(excluding `js` and `css`) will be copied by webpack's
`file-loader` into the `static/build` directory. In production, the plugin
`Flask-Static-Digest` zips the webpack content and tags them with a MD5 hash.
As a result, you must use the `static_url_for` function when including static content,
as it resolves the correct file name, including the MD5 hash.
For example

```html
<link rel="shortcut icon" href="{{static_url_for('static', filename='build/img/favicon.ico') }}">
```

If all of your static files are managed this way, then their filenames will change whenever their
contents do, and you can ask Flask to tell web browsers that they
should cache all your assets forever by including the following line
in ``.env``:

```text
SEND_FILE_MAX_AGE_DEFAULT=31556926  # one year
```
