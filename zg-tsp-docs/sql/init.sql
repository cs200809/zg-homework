-- ============================================================================
-- zg-tsp 数据库初始化脚本
--
-- 本文件由 `python -m app.seed.export_ddl` **自动生成**，请勿手工编辑。
-- 权威来源：`zg-tsp-server/app/models/entities.py`（14 张表）。
-- 改了 ORM 后重新执行该脚本以保持同步。
--
-- 用法（推荐经 scripts/init.sh，它会替换 admin 密码占位符）：
--     mysql --default-character-set=utf8mb4 <库名> < init.sql
--
-- 说明：
--   · 全部语句幂等，可重复执行
--   · FOREIGN_KEY_CHECKS=0/1 用于绕开 users ↔ classes 的循环外键依赖
--   · admin 密码以占位符 __ADMIN_BCRYPT_HASH__ 写入，
--     直接用 mysql 导入会导致 admin 无法登录，必须经 scripts/init.sh
-- ============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

-- --- classes ---
CREATE TABLE IF NOT EXISTS `classes` (
	id INTEGER NOT NULL COMMENT '班级ID' AUTO_INCREMENT,
	name VARCHAR(50) NOT NULL COMMENT '班级名称',
	invite_code VARCHAR(8) NOT NULL COMMENT '班级邀请码，学生加入时使用',
	teacher_id INTEGER NOT NULL COMMENT '班主任用户ID',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	UNIQUE (invite_code),
	FOREIGN KEY(teacher_id) REFERENCES users (id)
)COMMENT='班级表：老师创建，学生凭邀请码加入';

-- --- users ---
CREATE TABLE IF NOT EXISTS `users` (
	id INTEGER NOT NULL COMMENT '用户ID' AUTO_INCREMENT,
	username VARCHAR(20) NOT NULL COMMENT '用户名，唯一，3~20 位',
	password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希（bcrypt），绝不明文存储',
	`role` VARCHAR(10) NOT NULL COMMENT '角色：admin/teacher/student/parent',
	nickname VARCHAR(30) COMMENT '昵称',
	avatar VARCHAR(255) COMMENT '头像地址',
	class_id INTEGER COMMENT '所属班级ID，学生用',
	bind_code VARCHAR(8) COMMENT '学生绑定码，家长凭此绑定孩子',
	total_points INTEGER NOT NULL DEFAULT 0 COMMENT '积分余额，不可为负',
	status VARCHAR(10) NOT NULL DEFAULT 'active' COMMENT '状态：active 启用 / disabled 禁用',
	must_change_password BOOL NOT NULL DEFAULT 0 COMMENT '是否强制改密（admin首登、重置密码后为1）',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	UNIQUE (username),
	FOREIGN KEY(class_id) REFERENCES classes (id),
	KEY `ix_users_class_id` (class_id)
)COMMENT='用户表：admin/teacher/student/parent 四角色账号';

-- --- admin_logs ---
CREATE TABLE IF NOT EXISTS `admin_logs` (
	id INTEGER NOT NULL COMMENT '日志ID' AUTO_INCREMENT,
	admin_id INTEGER NOT NULL COMMENT '操作人（admin）用户ID',
	action VARCHAR(50) NOT NULL COMMENT '操作标识，如 user_disable / rule_update',
	target_type VARCHAR(30) COMMENT '操作对象类型：user / point_rule / teacher_invite_code / article',
	target_id INTEGER COMMENT '操作对象ID',
	detail TEXT COMMENT '操作详情（JSON 或描述）',
	created_at DATETIME NOT NULL COMMENT '操作时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(admin_id) REFERENCES users (id)
)COMMENT='管理员操作审计表：禁用、规则修改、文章删除等敏感操作留痕';

-- --- articles ---
CREATE TABLE IF NOT EXISTS `articles` (
	id INTEGER NOT NULL COMMENT '文章ID' AUTO_INCREMENT,
	author_id INTEGER NOT NULL COMMENT '作者用户ID',
	created_role VARCHAR(10) COMMENT '作者角色：teacher / admin',
	title VARCHAR(100) NOT NULL COMMENT '文章标题',
	cover VARCHAR(255) COMMENT '封面图地址',
	content TEXT NOT NULL COMMENT '正文内容',
	file_url VARCHAR(255) COMMENT '原始上传文件路径（迭代 v2.1）',
	file_name VARCHAR(255) COMMENT '原始文件名（迭代 v2.1）',
	file_type VARCHAR(20) COMMENT '原始文件类型：pdf / docx（迭代 v2.1）',
	status VARCHAR(10) NOT NULL DEFAULT 'published' COMMENT '状态：published 已发布 / hidden 已隐藏（学生端仅见 published）',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	updated_at DATETIME COMMENT '最后更新时间',
	PRIMARY KEY (id),
	FOREIGN KEY(author_id) REFERENCES users (id)
)COMMENT='文章表：课后阅读材料，teacher/admin 均可发布';

-- --- checkins ---
CREATE TABLE IF NOT EXISTS `checkins` (
	id INTEGER NOT NULL COMMENT '签到ID' AUTO_INCREMENT,
	student_id INTEGER NOT NULL COMMENT '学生用户ID',
	checkin_date DATE NOT NULL COMMENT '签到日期',
	points INTEGER COMMENT '本次获得积分（读 checkin_daily 规则）',
	streak INTEGER COMMENT '连续签到天数，用于连续7天额外奖励',
	PRIMARY KEY (id),
	CONSTRAINT uq_checkin_day UNIQUE (student_id, checkin_date),
	FOREIGN KEY(student_id) REFERENCES users (id)
)COMMENT='签到表：每日一次，同一天唯一';

-- --- game_records ---
CREATE TABLE IF NOT EXISTS `game_records` (
	id INTEGER NOT NULL COMMENT '记录ID' AUTO_INCREMENT,
	student_id INTEGER NOT NULL COMMENT '学生用户ID',
	game_type VARCHAR(20) COMMENT '游戏类型：sudoku 数独 / idiom 成语接龙',
	difficulty VARCHAR(10) COMMENT '难度：数独用 easy/medium/hard',
	score INTEGER COMMENT '游戏得分',
	points INTEGER COMMENT '本次获得积分',
	duration_seconds INTEGER COMMENT '游戏时长（秒）',
	play_date DATE COMMENT '游戏日期（用于每日上限统计）',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(student_id) REFERENCES users (id)
)COMMENT='游戏记录表：数独、成语接龙的成绩留痕';

-- --- homework ---
CREATE TABLE IF NOT EXISTS `homework` (
	id INTEGER NOT NULL COMMENT '作业ID' AUTO_INCREMENT,
	class_id INTEGER NOT NULL COMMENT '所属班级ID',
	teacher_id INTEGER NOT NULL COMMENT '布置老师用户ID',
	title VARCHAR(100) NOT NULL COMMENT '作业标题',
	description TEXT COMMENT '作业描述/题目内容',
	subject VARCHAR(20) COMMENT '科目：语文/数学/英语等',
	deadline DATETIME NOT NULL COMMENT '截止时间，超过判定为迟交',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(class_id) REFERENCES classes (id),
	FOREIGN KEY(teacher_id) REFERENCES users (id)
)COMMENT='作业表：老师布置';

-- --- idiom_questions ---
CREATE TABLE IF NOT EXISTS `idiom_questions` (
	id INTEGER NOT NULL COMMENT '题目ID' AUTO_INCREMENT,
	prompt VARCHAR(50) NOT NULL COMMENT '题干（上一个成语的末字或题目文本）',
	answer VARCHAR(50) NOT NULL COMMENT '正确答案',
	distractors TEXT COMMENT '干扰项（JSON 数组），建议≥2个，不足时服务端随机补齐',
	difficulty VARCHAR(10) NOT NULL DEFAULT 'normal' COMMENT '难度：normal / hard',
	enabled BOOL NOT NULL DEFAULT 1 COMMENT '是否启用；false 则学生端抽不到',
	created_by INTEGER COMMENT '导入人（admin）ID',
	created_at DATETIME NOT NULL COMMENT '导入时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(created_by) REFERENCES users (id),
	KEY `ix_idiom_enabled` (enabled)
)COMMENT='成语接龙题库表：由 admin 后台导入';

-- --- parent_students ---
CREATE TABLE IF NOT EXISTS `parent_students` (
	id INTEGER NOT NULL COMMENT '关系ID' AUTO_INCREMENT,
	parent_id INTEGER NOT NULL COMMENT '家长用户ID',
	student_id INTEGER NOT NULL COMMENT '学生用户ID',
	PRIMARY KEY (id),
	CONSTRAINT uq_parent_student UNIQUE (parent_id, student_id),
	FOREIGN KEY(parent_id) REFERENCES users (id),
	FOREIGN KEY(student_id) REFERENCES users (id)
)COMMENT='家长-学生关系表：一个家长可绑多个孩子';

-- --- point_logs ---
CREATE TABLE IF NOT EXISTS `point_logs` (
	id INTEGER NOT NULL COMMENT '流水ID' AUTO_INCREMENT,
	student_id INTEGER NOT NULL COMMENT '学生用户ID',
	type VARCHAR(20) NOT NULL COMMENT '类型：checkin/homework/reading/game/consume（consume 为负数）',
	points INTEGER NOT NULL COMMENT '积分数值，正为发放、负为扣减',
	remark VARCHAR(255) COMMENT '备注说明',
	operator_id INTEGER COMMENT '操作人ID（家长扣分时为家长ID）',
	log_date DATE NOT NULL COMMENT '积分归属日期，用于日上限统计',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(student_id) REFERENCES users (id),
	FOREIGN KEY(operator_id) REFERENCES users (id),
	KEY `ix_point_logs_student_date` (student_id, log_date)
)COMMENT='积分流水表（核心）：所有积分变动必写，保证可追溯';

-- --- point_rules ---
CREATE TABLE IF NOT EXISTS `point_rules` (
	id INTEGER NOT NULL COMMENT '规则ID' AUTO_INCREMENT,
	rule_key VARCHAR(50) NOT NULL COMMENT '规则键，唯一且不可修改（如 checkin_daily）',
	rule_name VARCHAR(50) NOT NULL COMMENT '规则名称（展示用）',
	points INTEGER NOT NULL COMMENT '每次发放的积分数',
	daily_limit INTEGER COMMENT '每日次数上限；空表示不限。游戏规则为当日合计积分上限',
	extra_config TEXT COMMENT '扩展配置（JSON 字符串），如 {"single_article_limit":10}',
	enabled BOOL NOT NULL DEFAULT 1 COMMENT '是否启用；false 则不发放该积分',
	updated_by INTEGER COMMENT '最后修改人（admin）ID',
	updated_at DATETIME NOT NULL COMMENT '最后更新时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	UNIQUE (rule_key),
	FOREIGN KEY(updated_by) REFERENCES users (id),
	KEY `ix_point_rules_key` (rule_key)
)COMMENT='积分规则表：admin 可改，修改后立即生效（daily_limit 为每日次数上限）';

-- --- teacher_invite_codes ---
CREATE TABLE IF NOT EXISTS `teacher_invite_codes` (
	id INTEGER NOT NULL COMMENT '邀请码ID' AUTO_INCREMENT,
	code VARCHAR(12) NOT NULL COMMENT '邀请码，12 位随机字符',
	status VARCHAR(10) NOT NULL DEFAULT 'unused' COMMENT '状态：unused 未用 / used 已用 / expired 过期 / revoked 已撤销',
	created_by INTEGER NOT NULL COMMENT '发放人（admin）用户ID',
	used_by_user_id INTEGER COMMENT '使用者用户ID（使用后写入）',
	expire_at DATETIME COMMENT '过期时间，空表示不过期',
	created_at DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	used_at DATETIME COMMENT '使用时间（被注册时写入）',
	PRIMARY KEY (id),
	UNIQUE (code),
	FOREIGN KEY(created_by) REFERENCES users (id),
	FOREIGN KEY(used_by_user_id) REFERENCES users (id),
	KEY `ix_invite_code_status` (code, status)
)COMMENT='老师邀请码表：admin 发放，一码一用';

-- --- homework_records ---
CREATE TABLE IF NOT EXISTS `homework_records` (
	id INTEGER NOT NULL COMMENT '记录ID' AUTO_INCREMENT,
	homework_id INTEGER NOT NULL COMMENT '作业ID',
	student_id INTEGER NOT NULL COMMENT '学生用户ID',
	start_time DATETIME COMMENT '开始写作业时间，重复点击不覆盖',
	submit_time DATETIME COMMENT '提交时间',
	duration_minutes INTEGER COMMENT '用时（分钟）= 提交时间 - 开始时间；<1 分钟标记异常',
	status VARCHAR(10) COMMENT '状态：not_started 未开始 / doing 进行中 / submitted 已提交 / late 迟交',
	file_url VARCHAR(255) COMMENT '上传文件地址（jpg/png/pdf，≤10MB）',
	text_content TEXT COMMENT '文本作答内容',
	points INTEGER NOT NULL DEFAULT 0 COMMENT '本次获得的积分（读 point_rules）',
	PRIMARY KEY (id),
	CONSTRAINT uq_homework_student UNIQUE (homework_id, student_id),
	FOREIGN KEY(homework_id) REFERENCES homework (id),
	FOREIGN KEY(student_id) REFERENCES users (id),
	KEY `ix_homework_records_student` (student_id)
)COMMENT='作业记录表：学生开始/提交打点与用时统计';

-- --- reading_records ---
CREATE TABLE IF NOT EXISTS `reading_records` (
	id INTEGER NOT NULL COMMENT '记录ID' AUTO_INCREMENT,
	article_id INTEGER NOT NULL COMMENT '文章ID',
	student_id INTEGER NOT NULL COMMENT '学生用户ID',
	duration_seconds INTEGER NOT NULL DEFAULT 0 COMMENT '有效阅读时长（秒），仅累计通过心跳校验的时段',
	finished BOOL NOT NULL DEFAULT 0 COMMENT '是否读完（滚动到底标记）',
	points INTEGER NOT NULL DEFAULT 0 COMMENT '本次阅读获得积分',
	read_date DATE COMMENT '阅读日期（按日去重）',
	PRIMARY KEY (id),
	CONSTRAINT uq_reading_day UNIQUE (article_id, student_id, read_date),
	FOREIGN KEY(article_id) REFERENCES articles (id),
	FOREIGN KEY(student_id) REFERENCES users (id)
)COMMENT='阅读记录表：按时长积分，需心跳防挂机校验';

-- --- 积分规则种子（PRD 4.2）---
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'checkin_daily', '每日签到', 5, 1, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'checkin_daily');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'checkin_streak_7', '连续签到7天', 10, 1, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'checkin_streak_7');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'homework_on_time', '作业按时提交', 10, NULL, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'homework_on_time');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'homework_late', '作业迟交', 5, NULL, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'homework_late');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'reading_per_minute', '阅读每分钟', 1, 30, '{"single_article_limit": 10}', 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'reading_per_minute');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'reading_finish', '读完文章', 5, NULL, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'reading_finish');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'game_sudoku_easy', '数独-简单', 5, 20, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'game_sudoku_easy');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'game_sudoku_medium', '数独-中等', 10, 20, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'game_sudoku_medium');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'game_sudoku_hard', '数独-困难', 15, 20, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'game_sudoku_hard');
INSERT INTO point_rules (rule_key, rule_name, points, daily_limit, extra_config, enabled)
SELECT 'game_idiom', '成语接龙每题', 1, 20, NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM point_rules WHERE rule_key = 'game_idiom');

-- --- admin 账户 ---
INSERT INTO users (username, password_hash, role, nickname, total_points, status, must_change_password)
SELECT 'admin', '__ADMIN_BCRYPT_HASH__', 'admin', '超级管理员', 0, 'active', 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

SET FOREIGN_KEY_CHECKS=1;
