CREATE TABLE `cashflow` (
`id` int(11) NOT NULL,
`uid` int(11) NULL DEFAULT NULL COMMENT '购买用户',
`fid` int(11) NULL DEFAULT NULL COMMENT '所购买的基金',
`amount` int(10) NULL DEFAULT NULL COMMENT '购买金额',
`date` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '购买日期（确认日期）',
`comment` varchar(30) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '复盘备注',
`type` tinyint(1) NULL,
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `dailyworth` (
`id` int(11) NOT NULL,
`fid` int(11) NULL DEFAULT NULL COMMENT '基金编号',
`pirce` float NULL DEFAULT NULL,
`date` date NULL DEFAULT NULL COMMENT '日期',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `fund` (
`id` int(11) NOT NULL,
`name` varchar(30) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '基金名称',
`fund_code` int(11) NULL DEFAULT NULL,
`type` tinyint(4) NULL DEFAULT NULL COMMENT '基金类型',
`co_id` tinyint(4) NULL DEFAULT NULL COMMENT '所属基金公司',
PRIMARY KEY (`id`) ,
UNIQUE INDEX `fund_code` (`fund_code` ASC) USING BTREE
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `fundco` (
`id` int(11) NOT NULL,
`name` varchar(30) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL,
`co_id` varchar(10) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '基金公司编号',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `fundmgr` (
`id` int(11) NOT NULL,
`mgr_id` int(10) NULL DEFAULT NULL COMMENT '经理编号',
`name` varchar(4) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '经理名称',
`co_id` int(10) NULL DEFAULT NULL COMMENT '所属公司',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `handpick` (
`id` int(11) NOT NULL,
`uid` int(11) NULL DEFAULT NULL COMMENT '用户编号',
`fid` int(11) NULL DEFAULT NULL COMMENT '基金编号',
`pick_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '收藏时间',
`comment` varchar(30) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '备注',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `inoutrate` (
`id` int(11) NOT NULL,
`fid` int(11) NULL DEFAULT NULL COMMENT '基金编号',
`rule_id` int(11) NULL DEFAULT NULL COMMENT '费率编号',
`rate` int(10) NULL DEFAULT NULL COMMENT '费率百分比',
`type` tinyint(1) NULL,
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `inrule` (
`id` int(11) NOT NULL,
`start_quota` tinyint(4) NULL DEFAULT NULL COMMENT '计费开始额度',
`end_quota` tinyint(4) NULL DEFAULT NULL COMMENT '计费结束额度',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `mgrlog` (
`id` int(11) NOT NULL,
`fid` int(11) NULL DEFAULT NULL COMMENT '基金编号',
`mgr_id` int(11) NULL DEFAULT NULL COMMENT '基金经理编号',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `outrule` (
`id` int(11) NOT NULL,
`start_day` tinyint(4) NULL DEFAULT NULL COMMENT '计费开始天数',
`end_day` tinyint(4) NULL DEFAULT NULL COMMENT '计费结束天数',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;
CREATE TABLE `user` (
`id` int(11) NOT NULL COMMENT '用户编号',
`name` varchar(16) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '用户名',
`password` varchar(40) CHARACTER SET latin1 COLLATE latin1_swedish_ci NOT NULL COMMENT '用户密码',
`email` varchar(30) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '注册邮箱',
`phone_num` varchar(11) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '注册手机号',
`avatar` varchar(60) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL DEFAULT NULL COMMENT '用户头像或自动生成',
`create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '注册时间',
PRIMARY KEY (`id`)
)
ENGINE = InnoDB
AUTO_INCREMENT = 0
AVG_ROW_LENGTH = 0
DEFAULT CHARACTER SET = latin1
COLLATE = latin1_swedish_ci
KEY_BLOCK_SIZE = 0
MAX_ROWS = 0
MIN_ROWS = 0
ROW_FORMAT = Dynamic;

ALTER TABLE `cashflow` ADD CONSTRAINT `fk_cashflow_user_1` FOREIGN KEY (`uid`) REFERENCES `user` (`id`);
ALTER TABLE `user` ADD CONSTRAINT `fk_user_handpick_1` FOREIGN KEY (`id`) REFERENCES `handpick` (`uid`);
ALTER TABLE `fund` ADD CONSTRAINT `fk_fund_handpick_1` FOREIGN KEY (`id`) REFERENCES `handpick` (`fid`);
ALTER TABLE `fundco` ADD CONSTRAINT `fk_fundco_fund_1` FOREIGN KEY (`id`) REFERENCES `fund` (`co_id`);
ALTER TABLE `fundmgr` ADD CONSTRAINT `fk_fundmgr_mgrlog_1` FOREIGN KEY (`id`) REFERENCES `mgrlog` (`mgr_id`);
ALTER TABLE `fund` ADD CONSTRAINT `fk_fund_mgrlog_1` FOREIGN KEY (`id`) REFERENCES `mgrlog` (`fid`);
ALTER TABLE `fund` ADD CONSTRAINT `fk_fund_dailyworth_1` FOREIGN KEY (`id`) REFERENCES `dailyworth` (`fid`);
ALTER TABLE `fund` ADD CONSTRAINT `fk_fund_inrate_1` FOREIGN KEY (`id`) REFERENCES `inoutrate` (`fid`);
ALTER TABLE `user` ADD CONSTRAINT `fk_user_cashflow_1` FOREIGN KEY (`id`) REFERENCES `cashflow` (`uid`);
ALTER TABLE `fund` ADD CONSTRAINT `fk_fund_cashflow_1` FOREIGN KEY (`id`) REFERENCES `cashflow` (`fid`);
ALTER TABLE `inrule` ADD CONSTRAINT `fk_inrule_inoutrate_1` FOREIGN KEY (`id`) REFERENCES `inoutrate` (`rule_id`);
ALTER TABLE `outrule` ADD CONSTRAINT `fk_outrule_inoutrate_1` FOREIGN KEY (`id`) REFERENCES `inoutrate` (`rule_id`);
ALTER TABLE `fund` ADD CONSTRAINT `fk_fund_inoutrate_1` FOREIGN KEY (`id`) REFERENCES `inoutrate` (`fid`);
ALTER TABLE `fundco` ADD CONSTRAINT `fk_fundco_fundmgr_1` FOREIGN KEY (`id`) REFERENCES `fundmgr` (`co_id`);

