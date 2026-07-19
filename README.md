# 叽咕

> 基金理财的好伙伴！

[![Badge](https://img.shields.io/badge/link-996.icu-%23FF4D5B.svg?style=flat-square)](https://996.icu/#/en_US)
[![LICENSE](https://img.shields.io/badge/license-Anti%20996-blue.svg?style=flat-square)](https://github.com/996icu/996.ICU/blob/master/LICENSE)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)


```bash

      ___           ___           ___                                  ___           ___                         ___
     /\__\         /\  \         /\  \         _____                  /\  \         /\  \                       /\__\
    /:/ _/_        \:\  \        \:\  \       /::\  \                |::\  \       /::\  \         ___         /:/ _/_
   /:/ /\__\        \:\  \        \:\  \     /:/\:\  \               |:|:\  \     /:/\:\  \       /\__\       /:/ /\__\
  /:/ /:/  /    ___  \:\  \   _____\:\  \   /:/  \:\__\            __|:|\:\  \   /:/ /::\  \     /:/  /      /:/ /:/ _/_
 /:/_/:/  /    /\  \  \:\__\ /::::::::\__\ /:/__/ \:|__|          /::::|_\:\__\ /:/_/:/\:\__\   /:/__/      /:/_/:/ /\__\
 \:\/:/  /     \:\  \ /:/  / \:\~~\~~\/__/ \:\  \ /:/  /          \:\~~\  \/__/ \:\/:/  \/__/  /::\  \      \:\/:/ /:/  /
  \::/__/       \:\  /:/  /   \:\  \        \:\  /:/  /            \:\  \        \::/__/      /:/\:\  \      \::/_/:/  /
   \:\  \        \:\/:/  /     \:\  \        \:\/:/  /              \:\  \        \:\  \      \/__\:\  \      \:\/:/  /
    \:\__\        \::/  /       \:\__\        \::/  /                \:\__\        \:\__\          \:\__\      \::/  /
     \/__/         \/__/         \/__/         \/__/                  \/__/         \/__/           \/__/       \/__/

```


以上标志由 [Text to ASCII Art Generator (TAAG)](http://patorjk.com/software/taag/) 生成。

基金管理计划。使用 Flask 和 Vue 构建一个实现基金记账功能的前后端分离 Web 应用

## 启动

### 后端
```
cd backend
pdm install
pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
```
### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

## 🍬 赞助

帮助我们走得更远！详情说明参阅：[打赏 | 叽咕](https://fund.masantu.com/donate/)

![支付宝支付（推荐）](https://www.masantu.com/img/alipay.jpg)
![微信支付](https://www.masantu.com/img/wechatpay.jpg)

```
fundmate
├─ 📁.github
│  ├─ 📁workflows
│  │  └─ 📄lint.yaml
│  └─ 📄dependabot.yml
├─ 📁.idea
│  ├─ 📁dataSources
│  ├─ 📁inspectionProfiles
│  │  ├─ 📄profiles_settings.xml
│  │  └─ 📄Project_Default.xml
│  ├─ 📄.gitignore
│  ├─ 📄encodings.xml
│  ├─ 📄modules.xml
│  ├─ 📄other.xml
│  ├─ 📄sshConfigs.xml
│  ├─ 📄vcs.xml
│  └─ 📄watcherTasks.xml
├─ 📁.pytest_cache
├─ 📁backend
│  ├─ 📁.pytest_cache
│  ├─ 📁db
│  │  └─ 📄fmt.sql
│  ├─ 📁fundmate
│  │  ├─ 📁account
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄deal_trades.py
│  │  │  ├─ 📄models.py
│  │  │  ├─ 📄schemas.py
│  │  │  ├─ 📄views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁collection
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄logics.py
│  │  │  ├─ 📄models.py
│  │  │  ├─ 📄schemas.py
│  │  │  ├─ 📄views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁data
│  │  │  ├─ 📁alipay
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄trans.py
│  │  │  │  ├─ 📄utils.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁amac
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁baostock
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄trade_datas.csv
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁chinawealth
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄products.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁danjuan
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄combination.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁dkhs
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁eastmoney
│  │  │  │  ├─ 📁FundCrawler
│  │  │  │  │  ├─ 📁image
│  │  │  │  │  │  ├─ 📄result-1.png
│  │  │  │  │  │  ├─ 📄result-2.png
│  │  │  │  │  │  └─ 📄result-3.png
│  │  │  │  │  ├─ 📄.gitignore
│  │  │  │  │  ├─ 📄CrawlingCore.py
│  │  │  │  │  ├─ 📄CrawlingFund.py
│  │  │  │  │  ├─ 📄DataStructure.py
│  │  │  │  │  ├─ 📄FakeUAGetter.py
│  │  │  │  │  ├─ 📄FundListProvider.py
│  │  │  │  │  ├─ 📄methods.py
│  │  │  │  │  ├─ 📄MonkeyTest.py
│  │  │  │  │  ├─ 📄Parser.py
│  │  │  │  │  ├─ 📄README.md
│  │  │  │  │  ├─ 📄requirements.txt
│  │  │  │  │  └─ 📄__init__.py
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄fund.json
│  │  │  │  ├─ 📄trade_day.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁efunds
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁fundb
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁howbuy
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄combination.py
│  │  │  │  ├─ 📄company.json
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁inject
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁jq
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁jsl
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁qieman
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄combination.py
│  │  │  │  ├─ 📄utils.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁sipf
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄confidence.py
│  │  │  │  ├─ 📄cvnvf.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁tencentwm
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄fund_trans_list.py
│  │  │  │  ├─ 📄trans.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁ten_jqka
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁utils
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄ratio.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁xa
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁yzyx
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄temp.html
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁zo
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄.gitignore
│  │  │  ├─ 📄all.json
│  │  │  ├─ 📄base.py
│  │  │  ├─ 📄cmp.py
│  │  │  ├─ 📄fund_fee_ratio.py
│  │  │  ├─ 📄fund_info.py
│  │  │  ├─ 📄fund_mgr.py
│  │  │  ├─ 📄fund_portfolios.py
│  │  │  ├─ 📄init_db.py
│  │  │  ├─ 📄TK1001.json
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁exts
│  │  │  ├─ 📁flask_loguru
│  │  │  │  ├─ 📁tests
│  │  │  │  │  ├─ 📁__pycache__
│  │  │  │  │  ├─ 📄test_configuration_logger.py
│  │  │  │  │  └─ 📄__init__.py
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄configuration_logger.py
│  │  │  │  ├─ 📄flask_loguru.py
│  │  │  │  ├─ 📄README.md
│  │  │  │  ├─ 📄setup.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁__pycache__
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁fund
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄base.py
│  │  │  ├─ 📄load_templates.py
│  │  │  ├─ 📄models.py
│  │  │  ├─ 📄schemas.py
│  │  │  ├─ 📄views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁libs
│  │  │  ├─ 📁cal
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄rate_of_return.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁dataklasses
│  │  │  │  ├─ 📁.github
│  │  │  │  │  └─ 📁workflows
│  │  │  │  │     └─ 📄python-package.yml
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄dataklasses.py
│  │  │  │  ├─ 📄perf.py
│  │  │  │  ├─ 📄README.md
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁drf
│  │  │  │  └─ 📄status.py
│  │  │  ├─ 📁fund_morning_star_crawler
│  │  │  │  ├─ 📁code-record
│  │  │  │  │  └─ 📄.gitkeep
│  │  │  │  ├─ 📁screenshot
│  │  │  │  │  ├─ 📄certain_stock_holder_detail.png
│  │  │  │  │  ├─ 📄fund_base.png
│  │  │  │  │  ├─ 📄fund_list.png
│  │  │  │  │  ├─ 📄fund_manager.png
│  │  │  │  │  ├─ 📄fund_season.png
│  │  │  │  │  ├─ 📄fund_statistic.png
│  │  │  │  │  ├─ 📄fund_stock.png
│  │  │  │  │  ├─ 📄high-score-funds.png
│  │  │  │  │  ├─ 📄qrcode_merge.png
│  │  │  │  │  └─ 📄top_50_2021_q1_vs_2020_q4.png
│  │  │  │  ├─ 📁sql
│  │  │  │  │  ├─ 📄anchor_plan_create.sql
│  │  │  │  │  └─ 📄anchor_plan_stock_create.sql
│  │  │  │  ├─ 📁src
│  │  │  │  │  ├─ 📁assets
│  │  │  │  │  │  └─ 📁star
│  │  │  │  │  │     ├─ 📄star0.gif
│  │  │  │  │  │     ├─ 📄star1.gif
│  │  │  │  │  │     ├─ 📄star2.gif
│  │  │  │  │  │     ├─ 📄star3.gif
│  │  │  │  │  │     ├─ 📄star4.gif
│  │  │  │  │  │     ├─ 📄star5.gif
│  │  │  │  │  │     └─ 📄tmp.gif
│  │  │  │  │  ├─ 📁db
│  │  │  │  │  │  └─ 📄connect.py
│  │  │  │  │  ├─ 📁fund_info
│  │  │  │  │  │  ├─ 📄api.py
│  │  │  │  │  │  ├─ 📄crawler.py
│  │  │  │  │  │  ├─ 📄csv.py
│  │  │  │  │  │  ├─ 📄statistic.py
│  │  │  │  │  │  ├─ 📄supplement.py
│  │  │  │  │  │  └─ 📄tiantian.py
│  │  │  │  │  ├─ 📁sql_model
│  │  │  │  │  │  ├─ 📄base_model.py
│  │  │  │  │  │  ├─ 📄fund_insert.py
│  │  │  │  │  │  ├─ 📄fund_query.py
│  │  │  │  │  │  ├─ 📄fund_update.py
│  │  │  │  │  │  └─ 📄stock_query.py
│  │  │  │  │  ├─ 📁utils
│  │  │  │  │  │  ├─ 📄cookies.py
│  │  │  │  │  │  ├─ 📄file_op.py
│  │  │  │  │  │  ├─ 📄index.py
│  │  │  │  │  │  ├─ 📄login.py
│  │  │  │  │  │  └─ 📄__init__.py
│  │  │  │  │  ├─ 📄acquire_fund_base.py
│  │  │  │  │  ├─ 📄acquire_fund_quarter.py
│  │  │  │  │  ├─ 📄acquire_fund_snapshot.py
│  │  │  │  │  ├─ 📄fund_info_supplement.py
│  │  │  │  │  ├─ 📄fund_statistic.py
│  │  │  │  │  ├─ 📄fund_strategy.py
│  │  │  │  │  └─ 📄__init__.py
│  │  │  │  ├─ 📄.env.example
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄.gitmodules
│  │  │  │  ├─ 📄.python-version
│  │  │  │  ├─ 📄main.py
│  │  │  │  ├─ 📄README.md
│  │  │  │  └─ 📄requirements.txt
│  │  │  ├─ 📁ivix
│  │  │  │  ├─ 📄base.py
│  │  │  │  ├─ 📄ivixx.csv
│  │  │  │  ├─ 📄LICENSE
│  │  │  │  ├─ 📄options.csv
│  │  │  │  ├─ 📄README.md
│  │  │  │  ├─ 📄shibor.csv
│  │  │  │  ├─ 📄test.py
│  │  │  │  ├─ 📄tradeday.csv
│  │  │  │  ├─ 📄vix.html
│  │  │  │  ├─ 📄__init__.py
│  │  │  │  └─ 📄中国波指.png
│  │  │  ├─ 📁pysnowflake
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄LICENSE
│  │  │  │  ├─ 📄README.md
│  │  │  │  └─ 📄snowflake.py
│  │  │  ├─ 📁redeem_fee
│  │  │  │  ├─ 📁img
│  │  │  │  │  └─ 📄example.png
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄data.xlsx
│  │  │  │  ├─ 📄figure.py
│  │  │  │  ├─ 📄fl.py
│  │  │  │  ├─ 📄fund_list.py
│  │  │  │  ├─ 📄hold.py
│  │  │  │  ├─ 📄LICENSE
│  │  │  │  ├─ 📄main.py
│  │  │  │  ├─ 📄README.md
│  │  │  │  ├─ 📄utils.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄convert.py
│  │  │  ├─ 📄dk_enums.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁public
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄schemas.py
│  │  │  ├─ 📄views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁user
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄models.py
│  │  │  ├─ 📄schemas.py
│  │  │  ├─ 📄views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁__pycache__
│  │  ├─ 📄.flaskenv
│  │  ├─ 📄app.py
│  │  ├─ 📄commands.py
│  │  ├─ 📄compat.py
│  │  ├─ 📄config.py
│  │  ├─ 📄custom_sql_types.py
│  │  ├─ 📄database.py
│  │  ├─ 📄errors.py
│  │  ├─ 📄excepts.py
│  │  ├─ 📄extensions.py
│  │  ├─ 📄schema_ext.py
│  │  ├─ 📄settings.py
│  │  ├─ 📄types.py
│  │  ├─ 📄utils.py
│  │  ├─ 📄view_ext.py
│  │  └─ 📄__init__.py
│  ├─ 📁htmlcov
│  ├─ 📁migrations
│  ├─ 📁requirements
│  │  ├─ 📄base.in
│  │  ├─ 📄base.txt
│  │  ├─ 📄dev.in
│  │  ├─ 📄dev.txt
│  │  ├─ 📄lint.in
│  │  ├─ 📄lint.txt
│  │  ├─ 📄prod.txt
│  │  ├─ 📄tests.in
│  │  ├─ 📄tests.txt
│  │  ├─ 📄typing.in
│  │  └─ 📄typing.txt
│  ├─ 📁shell_scripts
│  │  ├─ 📄auto_env.sh
│  │  └─ 📄supervisord_entrypoint.sh
│  ├─ 📁supervisord_programs
│  │  └─ 📄gunicorn.conf
│  ├─ 📁tests
│  │  ├─ 📁collection
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄collection_teardown.py
│  │  │  ├─ 📄test_collection_models.py
│  │  │  ├─ 📄test_collection_views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁data
│  │  │  ├─ 📁chinawealth
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄.gitignore
│  │  │  │  ├─ 📄test_china_wealth.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁danjuan
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄test_dj_base.py
│  │  │  │  └─ 📄test_dj_combination.py
│  │  │  ├─ 📁dkhs
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_dkhs_base.py
│  │  │  ├─ 📁eastmoney
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄test_em_base.py
│  │  │  │  └─ 📄test_trade_day.py
│  │  │  ├─ 📁fundb
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_fundb_base.py
│  │  │  ├─ 📁howbuy
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_hb_combination.py
│  │  │  ├─ 📁qieman
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_qm_combination.py
│  │  │  ├─ 📁sipf
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_confidence.py
│  │  │  ├─ 📁ten_jqka
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_jq_base.py
│  │  │  ├─ 📁utils
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄test_ratio.py
│  │  │  │  └─ 📄test_utils_base.py
│  │  │  ├─ 📁yzyx
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_yzyx_base.py
│  │  │  ├─ 📁zo
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  └─ 📄test_qgg_base.py
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄test_data.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁db_data
│  │  │  ├─ 📄fmp_schema_sqlite.sql
│  │  │  ├─ 📄fund_company.sql
│  │  │  ├─ 📄fund_type.sql
│  │  │  └─ 📄fund_variety.sql
│  │  ├─ 📁exts
│  │  │  └─ 📁flask_loguru
│  │  │     ├─ 📁__pycache__
│  │  │     ├─ 📄test_configuration_logger.py
│  │  │     └─ 📄__init__.py
│  │  ├─ 📁fund
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄test_fund_models.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁libs
│  │  │  ├─ 📁cal
│  │  │  │  ├─ 📁__pycache__
│  │  │  │  ├─ 📄test_rate_of_return.py
│  │  │  │  └─ 📄__init__.py
│  │  │  ├─ 📁__pycache__
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁test_apps
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁user
│  │  │  ├─ 📁__pycache__
│  │  │  ├─ 📄test_user_models.py
│  │  │  ├─ 📄test_user_views.py
│  │  │  └─ 📄__init__.py
│  │  ├─ 📁__pycache__
│  │  ├─ 📄conftest.py
│  │  ├─ 📄demo.csv
│  │  ├─ 📄etf.csv
│  │  ├─ 📄factories.py
│  │  ├─ 📄schemas.py
│  │  ├─ 📄settings.py
│  │  ├─ 📄test_api.py
│  │  ├─ 📄test_app.py
│  │  ├─ 📄test_commands.py
│  │  ├─ 📄test_config.py
│  │  ├─ 📄test_db.py
│  │  ├─ 📄test_errors.py
│  │  ├─ 📄test_utils.py
│  │  └─ 📄__init__.py
│  ├─ 📁venv
│  ├─ 📁__pycache__
│  ├─ 📄.env.example
│  ├─ 📄.eslintrc
│  ├─ 📄.flaskenv
│  ├─ 📄.flaskenv.sample
│  ├─ 📄.gitignore
│  ├─ 📄autoapp.py
│  ├─ 📄docker-compose.yml
│  ├─ 📄Dockerfile
│  ├─ 📄LICENSE
│  ├─ 📄openapi.json
│  ├─ 📄pdm.lock
│  ├─ 📄pyproject.toml
│  ├─ 📄README.md
│  ├─ 📄supervisord.conf
│  └─ 📄__init__.py
├─ 📁docs
│  ├─ 📁.vuepress
│  │  └─ 📄config.js
│  ├─ 📁api
│  │  ├─ 📄api-from-third-party.md
│  │  └─ 📄README.md
│  ├─ 📁dev
│  │  ├─ 📄acknowledgement.md
│  │  ├─ 📄apiflask-tutorial.md
│  │  ├─ 📄bookkeeping.md
│  │  ├─ 📄centos-install.md
│  │  ├─ 📄choices-for-sqlalchemy.md
│  │  ├─ 📄code-style-guide.md
│  │  ├─ 📄custome-restful.md
│  │  ├─ 📄db-choice.md
│  │  ├─ 📄deal-with-env-var-in-flask.md
│  │  ├─ 📄deploy-web-app.md
│  │  ├─ 📄docker-install.md
│  │  ├─ 📄env-install.md
│  │  ├─ 📄errors-vs-exceptions.md
│  │  ├─ 📄every-operate-leaves-a-log.md
│  │  ├─ 📄fe-design.md
│  │  ├─ 📄flask-admin.md
│  │  ├─ 📄flask-auth.md
│  │  ├─ 📄frontend-index.md
│  │  ├─ 📄function-ideas.md
│  │  ├─ 📄fund-fee-ratio.md
│  │  ├─ 📄fund-portfolio.md
│  │  ├─ 📄fundmate-love-echarts.md
│  │  ├─ 📄get-ready.md
│  │  ├─ 📄github-action.md
│  │  ├─ 📄glossary.md
│  │  ├─ 📄guideline.md
│  │  ├─ 📄import-trade-records.md
│  │  ├─ 📄oauth2.md
│  │  ├─ 📄operate-db.md
│  │  ├─ 📄python-typing.md
│  │  ├─ 📄README.md
│  │  ├─ 📄regain-a-sense-of-restful.md
│  │  ├─ 📄scheduler-tasks.md
│  │  ├─ 📄something-that-is-untested-is-broken.md
│  │  ├─ 📄speed-up.md
│  │  ├─ 📄sqlalchemy-usage.md
│  │  ├─ 📄structure-of-project.md
│  │  ├─ 📄validate-form.md
│  │  └─ 📄vip.md
│  ├─ 📁fallback
│  │  ├─ 📄about.md
│  │  ├─ 📄donate.md
│  │  ├─ 📄faq.md
│  │  ├─ 📄feedback.md
│  │  ├─ 📄privacy.md
│  │  ├─ 📄README.md
│  │  └─ 📄todo.md
│  ├─ 📁guide
│  │  ├─ 📄export-alipay.md
│  │  ├─ 📄import-efund.md
│  │  └─ 📄README.md
│  ├─ 📁pytest
│  │  ├─ 📄conftest.md
│  │  ├─ 📄fixture.md
│  │  ├─ 📄keywords.md
│  │  ├─ 📄mark.md
│  │  ├─ 📄parametrize.md
│  │  ├─ 📄pytest-cov.md
│  │  ├─ 📄questions.md
│  │  └─ 📄README.md
│  ├─ 📁thoughts
│  │  ├─ 📄my-favrivate.md
│  │  └─ 📄si-bi-qian.md
│  └─ 📄README.md
├─ 📁frontend
│  ├─ 📁.circleci
│  │  └─ 📄config.yml
│  ├─ 📁.github
│  │  ├─ 📁workflows
│  │  │  └─ 📄deploy.yml
│  │  ├─ 📄CODE_OF_CONDUCT.md
│  │  ├─ 📄COMMIT_CONVENTION.md
│  │  ├─ 📄CONTRIBUTING.md
│  │  ├─ 📄ISSUE_TEMPLATE.md
│  │  └─ 📄PULL_REQUEST_TEMPLATE.md
│  ├─ 📁.node-gyp
│  │  └─ 📁include
│  │     └─ 📁node
│  │        ├─ 📄node.h
│  │        └─ 📄v8.h
│  ├─ 📁build
│  ├─ 📁demo
│  │  └─ 📄dashboard.png
│  ├─ 📁mock
│  │  ├─ 📁role
│  │  │  ├─ 📄index.ts
│  │  │  └─ 📄routes.ts
│  │  ├─ 📄api.ts
│  │  ├─ 📄articles.ts
│  │  ├─ 📄mock-server.ts
│  │  ├─ 📄security.ts
│  │  ├─ 📄swagger.yml
│  │  ├─ 📄transactions.ts
│  │  ├─ 📄tsconfig.json
│  │  └─ 📄users.ts
│  ├─ 📁public
│  │  ├─ 📁img
│  │  │  └─ 📁icons
│  │  │     ├─ 📄android-chrome-192x192.png
│  │  │     ├─ 📄android-chrome-512x512.png
│  │  │     ├─ 📄android-chrome-maskable-192x192.png
│  │  │     ├─ 📄android-chrome-maskable-512x512.png
│  │  │     ├─ 📄apple-touch-icon-120x120.png
│  │  │     ├─ 📄apple-touch-icon-152x152.png
│  │  │     ├─ 📄apple-touch-icon-180x180.png
│  │  │     ├─ 📄apple-touch-icon-60x60.png
│  │  │     ├─ 📄apple-touch-icon-76x76.png
│  │  │     ├─ 📄apple-touch-icon.png
│  │  │     ├─ 📄favicon-16x16.png
│  │  │     ├─ 📄favicon-32x32.png
│  │  │     ├─ 📄msapplication-icon-144x144.png
│  │  │     ├─ 📄mstile-150x150.png
│  │  │     └─ 📄safari-pinned-tab.svg
│  │  ├─ 📁tinymce
│  │  │  ├─ 📁langs
│  │  │  │  ├─ 📄es.js
│  │  │  │  ├─ 📄it.js
│  │  │  │  ├─ 📄ja.js
│  │  │  │  ├─ 📄ko_KR.js
│  │  │  │  └─ 📄zh_CN.js
│  │  │  ├─ 📁skins
│  │  │  │  ├─ 📁fonts
│  │  │  │  │  └─ 📄tinymce-mobile.woff
│  │  │  │  ├─ 📄content.inline.min.css
│  │  │  │  ├─ 📄content.min.css
│  │  │  │  ├─ 📄content.mobile.min.css
│  │  │  │  ├─ 📄skin.min.css
│  │  │  │  ├─ 📄skin.mobile.min.css
│  │  │  │  └─ 📄skin.shadowdom.min.css
│  │  │  ├─ 📄emojis.min.js
│  │  │  └─ 📄README.md
│  │  ├─ 📄favicon.ico
│  │  ├─ 📄index.html
│  │  ├─ 📄manifest.json
│  │  └─ 📄robots.txt
│  ├─ 📁src
│  │  ├─ 📁api
│  │  │  ├─ 📄articles.ts
│  │  │  ├─ 📄portfolios.ts
│  │  │  ├─ 📄roles.ts
│  │  │  ├─ 📄transactions.ts
│  │  │  ├─ 📄types.d.ts
│  │  │  └─ 📄users.ts
│  │  ├─ 📁assets
│  │  │  ├─ 📁401-images
│  │  │  │  └─ 📄401.gif
│  │  │  ├─ 📁404-images
│  │  │  │  ├─ 📄404-cloud.png
│  │  │  │  └─ 📄404.png
│  │  │  └─ 📁custom-theme
│  │  │     ├─ 📁fonts
│  │  │     │  ├─ 📄element-icons.ttf
│  │  │     │  └─ 📄element-icons.woff
│  │  │     └─ 📄index.css
│  │  ├─ 📁components
│  │  │  ├─ 📁AvatarUpload
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁BackToTop
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Breadcrumb
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Charts
│  │  │  │  ├─ 📁mixins
│  │  │  │  │  └─ 📄resize.ts
│  │  │  │  ├─ 📄BarChart.vue
│  │  │  │  ├─ 📄LineChart.vue
│  │  │  │  └─ 📄MixedChart.vue
│  │  │  ├─ 📁DragableCard
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁DraggableKanban
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁DraggableList
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁DraggableSelect
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁DropdownMenu
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Dropzone
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁ErrorLog
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁GithubCorner
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Hamburger
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁HeaderSearch
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁JsonEditor
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁LangSelect
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁MarkdownEditor
│  │  │  │  ├─ 📄default-options.ts
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁MaterialInput
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Pagination
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁PanThumb
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁RightPanel
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Screenfull
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁SizeSelect
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Sticky
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁TextHoverEffect
│  │  │  │  └─ 📄Mallki.vue
│  │  │  ├─ 📁ThemePicker
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁Tinymce
│  │  │  │  ├─ 📁components
│  │  │  │  │  └─ 📄EditorImage.vue
│  │  │  │  ├─ 📄config.ts
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁UploadExcel
│  │  │  │  └─ 📄index.vue
│  │  │  └─ 📁UploadImage
│  │  │     └─ 📄index.vue
│  │  ├─ 📁directives
│  │  │  ├─ 📁clipboard
│  │  │  │  └─ 📄index.ts
│  │  │  ├─ 📁el-draggable-dialog
│  │  │  │  └─ 📄index.ts
│  │  │  ├─ 📁permission
│  │  │  │  └─ 📄index.ts
│  │  │  ├─ 📁waves
│  │  │  │  ├─ 📄index.ts
│  │  │  │  └─ 📄waves.css
│  │  │  └─ 📄index.ts
│  │  ├─ 📁filters
│  │  │  └─ 📄index.ts
│  │  ├─ 📁icons
│  │  │  ├─ 📁components
│  │  │  │  ├─ 📄404.ts
│  │  │  │  ├─ 📄back-top.ts
│  │  │  │  ├─ 📄bug.ts
│  │  │  │  ├─ 📄chart.ts
│  │  │  │  ├─ 📄clipboard.ts
│  │  │  │  ├─ 📄component.ts
│  │  │  │  ├─ 📄dashboard.ts
│  │  │  │  ├─ 📄documentation.ts
│  │  │  │  ├─ 📄drag.ts
│  │  │  │  ├─ 📄edit.ts
│  │  │  │  ├─ 📄education.ts
│  │  │  │  ├─ 📄email.ts
│  │  │  │  ├─ 📄example.ts
│  │  │  │  ├─ 📄excel.ts
│  │  │  │  ├─ 📄exit-fullscreen.ts
│  │  │  │  ├─ 📄eye-off.ts
│  │  │  │  ├─ 📄eye-on.ts
│  │  │  │  ├─ 📄form.ts
│  │  │  │  ├─ 📄fullscreen.ts
│  │  │  │  ├─ 📄guide-2.ts
│  │  │  │  ├─ 📄guide.ts
│  │  │  │  ├─ 📄hamburger.ts
│  │  │  │  ├─ 📄icon.ts
│  │  │  │  ├─ 📄index.ts
│  │  │  │  ├─ 📄international.ts
│  │  │  │  ├─ 📄language.ts
│  │  │  │  ├─ 📄like.ts
│  │  │  │  ├─ 📄link.ts
│  │  │  │  ├─ 📄list.ts
│  │  │  │  ├─ 📄lock.ts
│  │  │  │  ├─ 📄message.ts
│  │  │  │  ├─ 📄money.ts
│  │  │  │  ├─ 📄nested.ts
│  │  │  │  ├─ 📄password.ts
│  │  │  │  ├─ 📄pdf.ts
│  │  │  │  ├─ 📄people.ts
│  │  │  │  ├─ 📄peoples.ts
│  │  │  │  ├─ 📄qq.ts
│  │  │  │  ├─ 📄search.ts
│  │  │  │  ├─ 📄shopping.ts
│  │  │  │  ├─ 📄size.ts
│  │  │  │  ├─ 📄skill.ts
│  │  │  │  ├─ 📄star.ts
│  │  │  │  ├─ 📄tab.ts
│  │  │  │  ├─ 📄table.ts
│  │  │  │  ├─ 📄theme.ts
│  │  │  │  ├─ 📄tree-table.ts
│  │  │  │  ├─ 📄tree.ts
│  │  │  │  ├─ 📄user.ts
│  │  │  │  ├─ 📄wechat.ts
│  │  │  │  └─ 📄zip.ts
│  │  │  ├─ 📁svg
│  │  │  │  ├─ 📄404.svg
│  │  │  │  ├─ 📄back-top.svg
│  │  │  │  ├─ 📄bug.svg
│  │  │  │  ├─ 📄chart.svg
│  │  │  │  ├─ 📄clipboard.svg
│  │  │  │  ├─ 📄component.svg
│  │  │  │  ├─ 📄dashboard.svg
│  │  │  │  ├─ 📄documentation.svg
│  │  │  │  ├─ 📄drag.svg
│  │  │  │  ├─ 📄edit.svg
│  │  │  │  ├─ 📄education.svg
│  │  │  │  ├─ 📄email.svg
│  │  │  │  ├─ 📄example.svg
│  │  │  │  ├─ 📄excel.svg
│  │  │  │  ├─ 📄exit-fullscreen.svg
│  │  │  │  ├─ 📄eye-off.svg
│  │  │  │  ├─ 📄eye-on.svg
│  │  │  │  ├─ 📄form.svg
│  │  │  │  ├─ 📄fullscreen.svg
│  │  │  │  ├─ 📄guide-2.svg
│  │  │  │  ├─ 📄guide.svg
│  │  │  │  ├─ 📄hamburger.svg
│  │  │  │  ├─ 📄icon.svg
│  │  │  │  ├─ 📄international.svg
│  │  │  │  ├─ 📄language.svg
│  │  │  │  ├─ 📄like.svg
│  │  │  │  ├─ 📄link.svg
│  │  │  │  ├─ 📄list.svg
│  │  │  │  ├─ 📄lock.svg
│  │  │  │  ├─ 📄message.svg
│  │  │  │  ├─ 📄money.svg
│  │  │  │  ├─ 📄nested.svg
│  │  │  │  ├─ 📄password.svg
│  │  │  │  ├─ 📄pdf.svg
│  │  │  │  ├─ 📄people.svg
│  │  │  │  ├─ 📄peoples.svg
│  │  │  │  ├─ 📄qq.svg
│  │  │  │  ├─ 📄search.svg
│  │  │  │  ├─ 📄shopping.svg
│  │  │  │  ├─ 📄size.svg
│  │  │  │  ├─ 📄skill.svg
│  │  │  │  ├─ 📄star.svg
│  │  │  │  ├─ 📄tab.svg
│  │  │  │  ├─ 📄table.svg
│  │  │  │  ├─ 📄theme.svg
│  │  │  │  ├─ 📄tree-table.svg
│  │  │  │  ├─ 📄tree.svg
│  │  │  │  ├─ 📄user.svg
│  │  │  │  ├─ 📄wechat.svg
│  │  │  │  └─ 📄zip.svg
│  │  │  └─ 📄README.md
│  │  ├─ 📁lang
│  │  │  ├─ 📄en.ts
│  │  │  ├─ 📄es.ts
│  │  │  ├─ 📄index.ts
│  │  │  ├─ 📄it.ts
│  │  │  ├─ 📄ja.ts
│  │  │  ├─ 📄ko.ts
│  │  │  └─ 📄zh.ts
│  │  ├─ 📁layout
│  │  │  ├─ 📁components
│  │  │  │  ├─ 📁Navbar
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  ├─ 📁Settings
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  ├─ 📁Sidebar
│  │  │  │  │  ├─ 📄index.vue
│  │  │  │  │  ├─ 📄SidebarItem.vue
│  │  │  │  │  ├─ 📄SidebarItemLink.vue
│  │  │  │  │  └─ 📄SidebarLogo.vue
│  │  │  │  ├─ 📁TagsView
│  │  │  │  │  ├─ 📄index.vue
│  │  │  │  │  └─ 📄ScrollPane.vue
│  │  │  │  ├─ 📄AppMain.vue
│  │  │  │  └─ 📄index.ts
│  │  │  ├─ 📁mixin
│  │  │  │  └─ 📄resize.ts
│  │  │  └─ 📄index.vue
│  │  ├─ 📁pwa
│  │  │  ├─ 📁components
│  │  │  │  └─ 📄ServiceWorkerUpdatePopup.vue
│  │  │  ├─ 📄register-service-worker.ts
│  │  │  └─ 📄service-worker.js
│  │  ├─ 📁router
│  │  │  ├─ 📁modules
│  │  │  │  ├─ 📄charts.ts
│  │  │  │  ├─ 📄components.ts
│  │  │  │  ├─ 📄nested.ts
│  │  │  │  └─ 📄table.ts
│  │  │  └─ 📄index.ts
│  │  ├─ 📁store
│  │  │  ├─ 📁modules
│  │  │  │  ├─ 📄app.ts
│  │  │  │  ├─ 📄error-log.ts
│  │  │  │  ├─ 📄permission.ts
│  │  │  │  ├─ 📄settings.ts
│  │  │  │  ├─ 📄tags-view.ts
│  │  │  │  └─ 📄user.ts
│  │  │  └─ 📄index.ts
│  │  ├─ 📁styles
│  │  │  ├─ 📄element-variables.scss
│  │  │  ├─ 📄element-variables.scss.d.ts
│  │  │  ├─ 📄index.scss
│  │  │  ├─ 📄_mixins.scss
│  │  │  ├─ 📄_svgicon.scss
│  │  │  ├─ 📄_transition.scss
│  │  │  ├─ 📄_variables.scss
│  │  │  └─ 📄_variables.scss.d.ts
│  │  ├─ 📁utils
│  │  │  ├─ 📄clipboard.ts
│  │  │  ├─ 📄cookies.ts
│  │  │  ├─ 📄error-log.ts
│  │  │  ├─ 📄excel.ts
│  │  │  ├─ 📄index.ts
│  │  │  ├─ 📄permission.ts
│  │  │  ├─ 📄request.ts
│  │  │  ├─ 📄scroll-to.ts
│  │  │  ├─ 📄validate.ts
│  │  │  └─ 📄zip.ts
│  │  ├─ 📁views
│  │  │  ├─ 📁bookkeeping
│  │  │  │  ├─ 📁Record
│  │  │  │  │  ├─ 📁components
│  │  │  │  │  │  ├─ 📄Step1.vue
│  │  │  │  │  │  ├─ 📄Step2.vue
│  │  │  │  │  │  └─ 📄Step3.vue
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁charts
│  │  │  │  ├─ 📄bar-chart.vue
│  │  │  │  ├─ 📄line-chart.vue
│  │  │  │  └─ 📄mixed-chart.vue
│  │  │  ├─ 📁clipboard
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁components-demo
│  │  │  │  ├─ 📄avatar-upload.vue
│  │  │  │  ├─ 📄back-to-top.vue
│  │  │  │  ├─ 📄count-to.vue
│  │  │  │  ├─ 📄draggable-dialog.vue
│  │  │  │  ├─ 📄draggable-kanban.vue
│  │  │  │  ├─ 📄draggable-list.vue
│  │  │  │  ├─ 📄draggable-select.vue
│  │  │  │  ├─ 📄dropzone.vue
│  │  │  │  ├─ 📄json-editor.vue
│  │  │  │  ├─ 📄markdown.vue
│  │  │  │  ├─ 📄mixin.vue
│  │  │  │  ├─ 📄split-pane.vue
│  │  │  │  ├─ 📄sticky.vue
│  │  │  │  └─ 📄tinymce.vue
│  │  │  ├─ 📁dashboard
│  │  │  │  ├─ 📁admin
│  │  │  │  │  ├─ 📁components
│  │  │  │  │  │  ├─ 📁TodoList
│  │  │  │  │  │  │  ├─ 📄index.vue
│  │  │  │  │  │  │  └─ 📄Todo.vue
│  │  │  │  │  │  ├─ 📄BarChart.vue
│  │  │  │  │  │  ├─ 📄BoxCard.vue
│  │  │  │  │  │  ├─ 📄LineChart.vue
│  │  │  │  │  │  ├─ 📄PanelGroup.vue
│  │  │  │  │  │  ├─ 📄PieChart.vue
│  │  │  │  │  │  ├─ 📄RadarChart.vue
│  │  │  │  │  │  └─ 📄TransactionTable.vue
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📁CashFlow
│  │  │  │  │  │  ├─ 📁components
│  │  │  │  │  │  │  └─ 📄TabPane.vue
│  │  │  │  │  │  └─ 📄index.vue
│  │  │  │  │  ├─ 📄AccountProfit.vue
│  │  │  │  │  ├─ 📄AssetAllocation.vue
│  │  │  │  │  ├─ 📄AssetTable.vue
│  │  │  │  │  ├─ 📄InvestStyle.vue
│  │  │  │  │  ├─ 📄OverView.vue
│  │  │  │  │  ├─ 📄PanelGroup.vue
│  │  │  │  │  └─ 📄RaddarChart.vue
│  │  │  │  ├─ 📁editor
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁error-log
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📄ErrorTestA.vue
│  │  │  │  │  └─ 📄ErrorTestB.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁error-page
│  │  │  │  ├─ 📄401.vue
│  │  │  │  └─ 📄404.vue
│  │  │  ├─ 📁example
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📁Dropdown
│  │  │  │  │  │  ├─ 📄Comment.vue
│  │  │  │  │  │  ├─ 📄index.ts
│  │  │  │  │  │  ├─ 📄Platform.vue
│  │  │  │  │  │  └─ 📄SourceUrl.vue
│  │  │  │  │  ├─ 📄ArticleDetail.vue
│  │  │  │  │  └─ 📄Warning.vue
│  │  │  │  ├─ 📄create.vue
│  │  │  │  ├─ 📄edit.vue
│  │  │  │  └─ 📄list.vue
│  │  │  ├─ 📁excel
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📄AutoWidthOption.vue
│  │  │  │  │  ├─ 📄BookTypeOption.vue
│  │  │  │  │  └─ 📄FilenameOption.vue
│  │  │  │  ├─ 📄export-excel.vue
│  │  │  │  ├─ 📄merge-header.vue
│  │  │  │  ├─ 📄select-excel.vue
│  │  │  │  └─ 📄upload-excel.vue
│  │  │  ├─ 📁exchange
│  │  │  │  ├─ 📁Account
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  ├─ 📁Asset
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  └─ 📁Record
│  │  │  │     ├─ 📁components
│  │  │  │     │  ├─ 📄Step1.vue
│  │  │  │     │  ├─ 📄Step2.vue
│  │  │  │     │  └─ 📄Step3.vue
│  │  │  │     └─ 📄index.vue
│  │  │  ├─ 📁explore
│  │  │  │  └─ 📁FundPortfolio
│  │  │  │     └─ 📄index.vue
│  │  │  ├─ 📁FundMgr
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁guide
│  │  │  │  ├─ 📄index.vue
│  │  │  │  └─ 📄steps.ts
│  │  │  ├─ 📁i18n-demo
│  │  │  │  ├─ 📄index.vue
│  │  │  │  └─ 📄local.ts
│  │  │  ├─ 📁icons
│  │  │  │  ├─ 📄element-icons.ts
│  │  │  │  ├─ 📄index.vue
│  │  │  │  └─ 📄svg-icons.ts
│  │  │  ├─ 📁login
│  │  │  │  ├─ 📁components
│  │  │  │  │  └─ 📄SocialSignin.vue
│  │  │  │  ├─ 📄auth-redirect.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁nested
│  │  │  │  ├─ 📁menu1
│  │  │  │  │  ├─ 📁menu1-1
│  │  │  │  │  │  └─ 📄index.vue
│  │  │  │  │  ├─ 📁menu1-2
│  │  │  │  │  │  ├─ 📁menu1-2-1
│  │  │  │  │  │  │  └─ 📄index.vue
│  │  │  │  │  │  ├─ 📁menu1-2-2
│  │  │  │  │  │  │  └─ 📄index.vue
│  │  │  │  │  │  └─ 📄index.vue
│  │  │  │  │  ├─ 📁menu1-3
│  │  │  │  │  │  └─ 📄index.vue
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  └─ 📁menu2
│  │  │  │     └─ 📄index.vue
│  │  │  ├─ 📁pdf
│  │  │  │  ├─ 📄content.ts
│  │  │  │  ├─ 📄download.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁permission
│  │  │  │  ├─ 📁components
│  │  │  │  │  └─ 📄SwitchRoles.vue
│  │  │  │  ├─ 📄directive.vue
│  │  │  │  ├─ 📄page.vue
│  │  │  │  └─ 📄role.vue
│  │  │  ├─ 📁PickedFund
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁profile
│  │  │  │  ├─ 📁components
│  │  │  │  │  ├─ 📄Account.vue
│  │  │  │  │  ├─ 📄Activity.vue
│  │  │  │  │  ├─ 📄Timeline.vue
│  │  │  │  │  └─ 📄UserCard.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁redirect
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁tab
│  │  │  │  ├─ 📁components
│  │  │  │  │  └─ 📄TabPane.vue
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁table
│  │  │  │  ├─ 📁dynamic-table
│  │  │  │  │  ├─ 📁components
│  │  │  │  │  │  ├─ 📄FixedHeaderTable.vue
│  │  │  │  │  │  └─ 📄UnfixedHeaderTable.vue
│  │  │  │  │  └─ 📄index.vue
│  │  │  │  ├─ 📄complex-table.vue
│  │  │  │  ├─ 📄draggable-table.vue
│  │  │  │  ├─ 📄index.vue
│  │  │  │  └─ 📄inline-edit-table.vue
│  │  │  ├─ 📁theme
│  │  │  │  └─ 📄index.vue
│  │  │  ├─ 📁tree
│  │  │  │  └─ 📄index.vue
│  │  │  └─ 📁zip
│  │  │     └─ 📄index.vue
│  │  ├─ 📄App.vue
│  │  ├─ 📄main.ts
│  │  ├─ 📄permission.ts
│  │  ├─ 📄settings.ts
│  │  └─ 📄shims.d.ts
│  ├─ 📁tests
│  │  ├─ 📁.pytest_cache
│  │  └─ 📁unit
│  │     ├─ 📁components
│  │     │  └─ 📄Breadcrumb.spec.ts
│  │     └─ 📁utils
│  │        ├─ 📄parseTime.spec.ts
│  │        └─ 📄validate.spec.ts
│  ├─ 📄.browserslistrc
│  ├─ 📄.editorconfig
│  ├─ 📄.env.development
│  ├─ 📄.env.production
│  ├─ 📄.env.staging
│  ├─ 📄.eslintignore
│  ├─ 📄.eslintrc.js
│  ├─ 📄.gitignore
│  ├─ 📄babel.config.js
│  ├─ 📄jest.config.js
│  ├─ 📄LICENSE
│  ├─ 📄package.json
│  ├─ 📄postcss.config.js
│  ├─ 📄README-zh.md
│  ├─ 📄README.md
│  ├─ 📄tsconfig.json
│  ├─ 📄vue.config.js
│  └─ 📄yarn.lock
├─ 📁statics
│  ├─ 📄31e6910d4299311aedb82be4db07de20.jpg
│  ├─ 📄cc17a321601ee2ae8592a11e4181339a.jpg
│  └─ 📄基于B_S架构的股票交易系统设计与实现-李英德.pdf
├─ 📁venv
├─ 📄.gitignore
├─ 📄.pre-commit-config.yaml
├─ 📄change_user_info.sh
├─ 📄LICENSE
├─ 📄package.json
├─ 📄README.md
├─ 📄SECURITY.md
├─ 📄SPEC.md
├─ 📄vercel.json
└─ 📄yarn.lock
```
