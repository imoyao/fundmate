/*
 Navicat Premium Data Transfer

 Source Server         : fmp
 Source Server Type    : SQLite
 Source Server Version : 3035005
 Source Schema         : main

 Target Server Type    : SQLite
 Target Server Version : 3035005
 File Encoding         : 65001

 Date: 30/11/2022 22:25:40
*/

PRAGMA foreign_keys = false;

-- ----------------------------
-- Table structure for account
-- ----------------------------
DROP TABLE IF EXISTS "account";
CREATE TABLE "account" (
  "id" INTEGER NOT NULL,
  "created_at" DATETIME DEFAULT (CURRENT_TIMESTAMP),
  "account_code" VARCHAR(10),
  "name" VARCHAR(10),
  "creator_id" INTEGER NOT NULL,
  "desc" VARCHAR(300),
  "rich_desc" VARCHAR(1000),
  "account_type" INTEGER,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("creator_id") REFERENCES "users" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for account_transaction_record
-- ----------------------------
DROP TABLE IF EXISTS "account_transaction_record";
CREATE TABLE "account_transaction_record" (
  "id" INTEGER NOT NULL,
  "created_at" DATETIME DEFAULT (CURRENT_TIMESTAMP),
  "user_id" INTEGER NOT NULL,
  "op_type" INTEGER,
  "redeem_prod" VARCHAR(36),
  "purchase_prod" VARCHAR(36),
  "amount" NUMERIC(32,4),
  "charge_fee" NUMERIC(32,4),
  "launch_trans_date" DATETIME,
  "trans_confirm_date" DATE NOT NULL,
  "transaction_id" BIGINT,
  "record_code" VARCHAR(36),
  "record_date" DATETIME,
  "comment" VARCHAR(300),
  "plat_comment" VARCHAR(300),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for alembic_version
-- ----------------------------
DROP TABLE IF EXISTS "alembic_version";
CREATE TABLE "alembic_version" (
  "version_num" VARCHAR(32) NOT NULL,
  CONSTRAINT "alembic_version_pkc" PRIMARY KEY ("version_num")
);

-- ----------------------------
-- Table structure for daily_worth
-- ----------------------------
DROP TABLE IF EXISTS "daily_worth";
CREATE TABLE "daily_worth" (
  "id" INTEGER NOT NULL,
  "created_at" DATETIME DEFAULT (CURRENT_TIMESTAMP),
  "price" FLOAT,
  "date" DATE,
  "fund_id" INTEGER NOT NULL,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("fund_id") REFERENCES "funds" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for fee_ratio
-- ----------------------------
DROP TABLE IF EXISTS "fee_ratio";
CREATE TABLE "fee_ratio" (
  "id" INTEGER NOT NULL,
  "fund_id" INTEGER,
  "fund_code" VARCHAR(6),
  "purchase_rule_id" INTEGER,
  "redeem_rule_id" INTEGER,
  "fee_type" INTEGER NOT NULL,
  "rate" NUMERIC(3,2),
  "fee_amount" NUMERIC(6,2),
  "last_modified" TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("fund_id") REFERENCES "funds" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY ("purchase_rule_id") REFERENCES "purchase_rule" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY ("redeem_rule_id") REFERENCES "redeem_rule" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for fund_company
-- ----------------------------
DROP TABLE IF EXISTS "fund_company";
CREATE TABLE "fund_company" (
  "id" INTEGER NOT NULL,
  "code" VARCHAR(10),
  "name" VARCHAR(30),
  "create_date" DATETIME,
  "scale" NUMERIC(10,2),
  "abbr_capital_initial_phonetic_alphabet" VARCHAR(30),
  "tx_eval" INTEGER,
  "full_name" VARCHAR(30),
  "f_counts" INTEGER,
  "mgr" VARCHAR(10),
  "update_time" DATETIME,
  "last_modified" TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  PRIMARY KEY ("id")
);

-- ----------------------------
-- Table structure for fund_mgr
-- ----------------------------
DROP TABLE IF EXISTS "fund_mgr";
CREATE TABLE "fund_mgr" (
  "id" INTEGER NOT NULL,
  "fund_id" INTEGER,
  "mgr_id" INTEGER,
  "is_classic" BOOLEAN,
  "start_date" DATETIME,
  "end_date" DATETIME,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("fund_id") REFERENCES "funds" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY ("mgr_id") REFERENCES "mgrs" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for fund_portfolio
-- ----------------------------
DROP TABLE IF EXISTS "fund_portfolio";
CREATE TABLE "fund_portfolio" (
  "id" INTEGER NOT NULL,
  "created_at" DATETIME DEFAULT (CURRENT_TIMESTAMP),
  "portfolio_code" VARCHAR(10),
  "name" VARCHAR(30),
  "code" VARCHAR(30),
  "is_visible" BOOLEAN,
  "found_date" DATE,
  "mgr_code" VARCHAR(10),
  "platform" INTEGER,
  "risk_type" INTEGER,
  "annualized_rate_of_return" NUMERIC(7,4),
  "max_drawdown" NUMERIC(7,4),
  "sharpe" NUMERIC(3,2),
  "volatility" NUMERIC(7,4),
  "invest_rate_of_return" NUMERIC(7,4),
  "desc" VARCHAR(300),
  "rich_desc" VARCHAR(1000),
  "update_time" DATETIME,
  "last_adjust_date" DATE,
  PRIMARY KEY ("id"),
  UNIQUE ("code" ASC)
);

-- ----------------------------
-- Table structure for fund_portfolio_adjust_history
-- ----------------------------
DROP TABLE IF EXISTS "fund_portfolio_adjust_history";
CREATE TABLE "fund_portfolio_adjust_history" (
  "id" INTEGER NOT NULL,
  "portfolio_code" VARCHAR(30),
  "update_date" DATETIME,
  "adjust_id" BIGINT,
  "plat_trade_id" VARCHAR(120),
  "desc" VARCHAR(1500),
  PRIMARY KEY ("id")
);

-- ----------------------------
-- Table structure for fund_portfolio_hold_detail
-- ----------------------------
DROP TABLE IF EXISTS "fund_portfolio_hold_detail";
CREATE TABLE "fund_portfolio_hold_detail" (
  "id" INTEGER NOT NULL,
  "fd_code" VARCHAR(6),
  "adjust_id" BIGINT,
  "portion" NUMERIC(5,4),
  PRIMARY KEY ("id")
);

-- ----------------------------
-- Table structure for fund_portfolio_mgr
-- ----------------------------
DROP TABLE IF EXISTS "fund_portfolio_mgr";
CREATE TABLE "fund_portfolio_mgr" (
  "id" INTEGER NOT NULL,
  "code" VARCHAR(10),
  "name" VARCHAR(30),
  "plat_code" VARCHAR(30),
  "mgr_type" INTEGER NOT NULL,
  "mgr_avatar_url" VARCHAR(300),
  "platform" INTEGER,
  "desc" VARCHAR(300),
  PRIMARY KEY ("id"),
  UNIQUE ("code" ASC)
);

-- ----------------------------
-- Table structure for fund_sale_org
-- ----------------------------
DROP TABLE IF EXISTS "fund_sale_org";
CREATE TABLE "fund_sale_org" (
  "id" INTEGER NOT NULL,
  "org_id" INTEGER,
  "name" VARCHAR(30),
  "known_name" VARCHAR(10),
  "addr" VARCHAR(200),
  "org_type" VARCHAR(30),
  "date" VARCHAR(10),
  PRIMARY KEY ("id")
);

-- ----------------------------
-- Table structure for fund_type
-- ----------------------------
DROP TABLE IF EXISTS "fund_type";
CREATE TABLE "fund_type" (
  "id" INTEGER NOT NULL,
  "name" VARCHAR(255),
  "var_id" INTEGER,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("var_id") REFERENCES "fund_variety" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  UNIQUE ("name" ASC)
);

-- ----------------------------
-- Table structure for fund_variety
-- ----------------------------
DROP TABLE IF EXISTS "fund_variety";
CREATE TABLE "fund_variety" (
  "id" INTEGER NOT NULL,
  "name" VARCHAR(255),
  PRIMARY KEY ("id"),
  UNIQUE ("name" ASC)
);

-- ----------------------------
-- Table structure for funds
-- ----------------------------
DROP TABLE IF EXISTS "funds";
CREATE TABLE "funds" (
  "id" INTEGER NOT NULL,
  "fund_code" VARCHAR(6),
  "name" VARCHAR(30),
  "full_name" VARCHAR(40),
  "abbr_capital_initial_phonetic_alphabet" VARCHAR(30),
  "full_capital_phonetic_alphabet" VARCHAR(80),
  "fund_type_id" INTEGER,
  "fund_variety_id" INTEGER,
  "co_id" INTEGER,
  "create_time" DATE,
  "symbol_prefix" VARCHAR(2),
  "risk_level" INTEGER,
  "is_fe_charge_mode" BOOLEAN,
  "perf_comp_base" VARCHAR(200),
  "last_modified" TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("fund_type_id") REFERENCES "fund_type" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY ("fund_variety_id") REFERENCES "fund_variety" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY ("co_id") REFERENCES "fund_company" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  UNIQUE ("fund_code" ASC)
);

-- ----------------------------
-- Table structure for hand_pick
-- ----------------------------
DROP TABLE IF EXISTS "hand_pick";
CREATE TABLE "hand_pick" (
  "id" INTEGER NOT NULL,
  "user_id" INTEGER NOT NULL,
  "fund_code" VARCHAR(6),
  "pick_time" TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  "comment" VARCHAR(300),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for invest_product
-- ----------------------------
DROP TABLE IF EXISTS "invest_product";
CREATE TABLE "invest_product" (
  "id" INTEGER NOT NULL,
  "plt_code" VARCHAR(16),
  "prod_code" VARCHAR(12),
  "verified_code" VARCHAR(32),
  "prod_name" VARCHAR(255),
  "platform" VARCHAR(7),
  "prod_type" VARCHAR(17),
  PRIMARY KEY ("id"),
  UNIQUE ("prod_code" ASC)
);

-- ----------------------------
-- Table structure for mgrs
-- ----------------------------
DROP TABLE IF EXISTS "mgrs";
CREATE TABLE "mgrs" (
  "id" INTEGER NOT NULL,
  "mgr_code" INTEGER,
  "name" VARCHAR(30),
  "company_id" INTEGER,
  "work_days" INTEGER,
  "sum_scale" NUMERIC(8,2),
  "best_rt" NUMERIC(7,2),
  "last_modified" TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "fund_company" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for purchase_rule
-- ----------------------------
DROP TABLE IF EXISTS "purchase_rule";
CREATE TABLE "purchase_rule" (
  "id" INTEGER NOT NULL,
  "start_quota" NUMERIC(12,2),
  "end_quota" NUMERIC(12,2),
  PRIMARY KEY ("id")
);

-- ----------------------------
-- Table structure for redeem_rule
-- ----------------------------
DROP TABLE IF EXISTS "redeem_rule";
CREATE TABLE "redeem_rule" (
  "id" INTEGER NOT NULL,
  "start_day" INTEGER,
  "end_day" INTEGER,
  PRIMARY KEY ("id")
);

-- ----------------------------
-- Table structure for roles
-- ----------------------------
DROP TABLE IF EXISTS "roles";
CREATE TABLE "roles" (
  "id" INTEGER NOT NULL,
  "name" VARCHAR(80) NOT NULL,
  PRIMARY KEY ("id"),
  UNIQUE ("name" ASC)
);

-- ----------------------------
-- Table structure for user_role
-- ----------------------------
DROP TABLE IF EXISTS "user_role";
CREATE TABLE "user_role" (
  "user_id" INTEGER NOT NULL,
  "role_id" INTEGER NOT NULL,
  PRIMARY KEY ("user_id", "role_id"),
  FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY ("role_id") REFERENCES "roles" ("id") ON DELETE NO ACTION ON UPDATE NO ACTION
);

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS "users";
CREATE TABLE "users" (
  "created_at" DATETIME DEFAULT (CURRENT_TIMESTAMP),
  "id" INTEGER NOT NULL,
  "name" VARCHAR(16),
  "username" VARCHAR(16) NOT NULL,
  "password" VARCHAR(150) NOT NULL,
  "email" VARCHAR(30) NOT NULL,
  "phone_num" VARCHAR(11),
  "custom_avatar" VARCHAR(512),
  "is_confirmed" BOOLEAN,
  "is_admin" BOOLEAN,
  "is_vip" BOOLEAN,
  "profile" TEXT,
  "is_active" BOOLEAN,
  "last_login" TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
  PRIMARY KEY ("id"),
  UNIQUE ("username" ASC),
  UNIQUE ("email" ASC)
);

-- ----------------------------
-- Indexes structure for table fee_ratio
-- ----------------------------
CREATE INDEX "ix_fee_ratio_fee_type"
ON "fee_ratio" (
  "fee_type" ASC
);

-- ----------------------------
-- Indexes structure for table fund_portfolio_adjust_history
-- ----------------------------
CREATE INDEX "ix_fund_portfolio_adjust_history_adjust_id"
ON "fund_portfolio_adjust_history" (
  "adjust_id" ASC
);
CREATE INDEX "ix_fund_portfolio_adjust_history_portfolio_code"
ON "fund_portfolio_adjust_history" (
  "portfolio_code" ASC
);

PRAGMA foreign_keys = true;
