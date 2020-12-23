CREATE TABLE IF NOT EXISTS user (
	user_id INT PRIMARY KEY COMMENT '用户编号',
	name VARCHAR(16) COMMENT '用户名',
	password VARCHAR(40) NOT NULL COMMENT '用户密码',
	email VARCHAR(16) COMMENT '注册邮箱',
	phone_num VARCHAR(11) COMMENT '注册手机号',
	create_time TIMESTAMP COMMENT '注册时间'
);

ALTER TABLE user
	ADD CONSTRAINT user_user_id_fk0 FOREIGN KEY (user_id) REFERENCES purchase (uid);

ALTER TABLE user
	ADD CONSTRAINT user_user_id_fk1 FOREIGN KEY (user_id) REFERENCES redeem (uid);

ALTER TABLE user
	ADD CONSTRAINT user_name_fk0 FOREIGN KEY (name) REFERENCES handpick (uid);

CREATE TABLE IF NOT EXISTS handpick (
	id int PRIMARY KEY,
	uid VARCHAR(20) COMMENT '用户编号',
	fid VARCHAR(20) COMMENT '基金编号',
	pick_time TIMESTAMP COMMENT '收藏时间',
	comment VARCHAR(30) COMMENT '备注'
);

CREATE TABLE IF NOT EXISTS fund (
	id int PRIMARY KEY,
	name VARCHAR(30) COMMENT '基金名称',
	fund_code INT(6) UNIQUE,
	type TINYINT COMMENT '基金类型',
	co_id TINYINT COMMENT '所属基金公司'
);

ALTER TABLE fund
	ADD CONSTRAINT fund_fund_code_fk0 FOREIGN KEY (fund_code) REFERENCES outrate (fid);

ALTER TABLE fund
	ADD CONSTRAINT fund_fund_code_fk1 FOREIGN KEY (fund_code) REFERENCES dailyworth (fid);

ALTER TABLE fund
	ADD CONSTRAINT fund_fund_code_fk2 FOREIGN KEY (fund_code) REFERENCES handpick (fid);

ALTER TABLE fund
	ADD CONSTRAINT fund_fund_code_fk3 FOREIGN KEY (fund_code) REFERENCES inrate (fid);

ALTER TABLE fund
	ADD CONSTRAINT fund_fund_code_fk4 FOREIGN KEY (fund_code) REFERENCES purchase (fid);

ALTER TABLE fund
	ADD CONSTRAINT fund_fund_code_fk5 FOREIGN KEY (fund_code) REFERENCES mgrlog (fid);

CREATE TABLE IF NOT EXISTS dailyworth (
	id int PRIMARY KEY,
	fid INT(6) COMMENT '基金编号',
	pirce FLOAT,
	date DATE COMMENT '日期'
);

CREATE TABLE IF NOT EXISTS fundmgr (
	id int PRIMARY KEY,
	mgr_id INT(10) COMMENT '经理编号',
	name VARCHAR(4) COMMENT '经理名称',
	co_id INT(10) COMMENT '所属公司'
);

ALTER TABLE fundmgr
	ADD CONSTRAINT fundmgr_mgr_id_fk0 FOREIGN KEY (mgr_id) REFERENCES mgrlog (mgr_id);

CREATE TABLE IF NOT EXISTS fundco (
	id int PRIMARY KEY,
	name VARCHAR(30),
	co_id VARCHAR(10) COMMENT '基金公司编号'
);

ALTER TABLE fundco
	ADD CONSTRAINT fundco_id_fk0 FOREIGN KEY (id) REFERENCES fund (co_id);

ALTER TABLE fundco
	ADD CONSTRAINT fundco_id_fk1 FOREIGN KEY (id) REFERENCES fundmgr (co_id);

CREATE TABLE IF NOT EXISTS mgrlog (
	id int PRIMARY KEY,
	fid INT(6) COMMENT '基金编号',
	mgr_id INT(10) COMMENT '基金经理编号'
);

CREATE TABLE IF NOT EXISTS purchase (
	id int PRIMARY KEY,
	uid VARCHAR(10) COMMENT '购买用户',
	fid INT(6) COMMENT '所购买的基金',
	amount INT(10) COMMENT '购买金额',
	date DATE DEFAULT current_date COMMENT '购买日期（确认日期）',
	comment VARCHAR(30) COMMENT '复盘备注'
);

CREATE TABLE IF NOT EXISTS redeem (
	id int PRIMARY KEY,
	uid INT(10) COMMENT '购买用户',
	fid VARCHAR(10) COMMENT '所购买的基金编号',
	amount INT(10) COMMENT '购买金额',
	date DATE COMMENT '赎回日期',
	comment VARCHAR(30) COMMENT '复盘备注'
);

CREATE TABLE IF NOT EXISTS inrule (
	id int PRIMARY KEY,
	start_quota TINYINT COMMENT '计费开始额度',
	end_quota TINYINT COMMENT '计费结束额度'
);

ALTER TABLE inrule
	ADD CONSTRAINT inrule_id_fk0 FOREIGN KEY (id) REFERENCES inrate (rule_id);

CREATE TABLE IF NOT EXISTS outrule (
	id int PRIMARY KEY,
	start_day TINYINT COMMENT '计费开始天数',
	end_day TINYINT COMMENT '计费结束天数'
);

ALTER TABLE outrule
	ADD CONSTRAINT outrule_id_fk0 FOREIGN KEY (id) REFERENCES outrate (rule_id);

CREATE TABLE IF NOT EXISTS inrate (
	id int PRIMARY KEY,
	fid INT(6) COMMENT '基金编号',
	rule_id INT(10) COMMENT '费率编号',
	rate INT(10) COMMENT '费率百分比'
);

CREATE TABLE IF NOT EXISTS outrate (
	id int PRIMARY KEY,
	rule_id INT(10) COMMENT '费率编号',
	fid INT(6) COMMENT '基金编号',
	rate INT(10) COMMENT '费率百分比'
) COMMENT = '卖出费率表';