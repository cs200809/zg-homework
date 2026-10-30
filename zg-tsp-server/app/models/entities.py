"""SQLAlchemy 模型 —— 对应 PRD 4.1 建表 SQL。

命名、类型、约束、索引均按 PRD 4.1；每个字段与表都带中文 COMMENT，
便于直接用 MySQL 客户端查看表结构时理解语义。

注意：MySQL 不支持真正的 BOOLEAN，统一用 `Boolean`（映射为 TINYINT(1)）；
JSON 字段用 `Text` 存储 JSON 字符串，保持与 PRD 建表 SQL 一致。
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有表的基类。"""


# --- users ---
class User(Base):
    """用户表：四角色账号（admin/teacher/student/parent）。"""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_class_id", "class_id"),
        {"comment": "用户表：admin/teacher/student/parent 四角色账号"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="用户ID")
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, comment="用户名，唯一，3~20 位")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希（bcrypt），绝不明文存储")
    role: Mapped[str] = mapped_column(String(10), nullable=False, comment="角色：admin/teacher/student/parent")
    nickname: Mapped[str | None] = mapped_column(String(30), comment="昵称")
    avatar: Mapped[str | None] = mapped_column(String(255), comment="头像地址")
    class_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classes.id"), comment="所属班级ID，学生用")
    bind_code: Mapped[str | None] = mapped_column(String(8), comment="学生绑定码，家长凭此绑定孩子")
    total_points: Mapped[int] = mapped_column(Integer, default=0, comment="积分余额，不可为负")
    status: Mapped[str] = mapped_column(String(10), default="active", comment="状态：active 启用 / disabled 禁用")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否强制改密（admin首登、重置密码后为1）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


# --- classes ---
class Class(Base):
    """班级表：老师创建，学生凭邀请码加入（决策 3：学生只属一个班级）。"""

    __tablename__ = "classes"
    __table_args__ = (
        {"comment": "班级表：老师创建，学生凭邀请码加入"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="班级ID")
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="班级名称")
    invite_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, comment="班级邀请码，学生加入时使用")
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="班主任用户ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<Class {self.name}>"


# --- teacher_invite_codes ---
class TeacherInviteCode(Base):
    """老师邀请码表：admin 发放，一码一用。"""

    __tablename__ = "teacher_invite_codes"
    __table_args__ = (
        Index("ix_invite_code_status", "code", "status"),
        {"comment": "老师邀请码表：admin 发放，一码一用"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="邀请码ID")
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, comment="邀请码，12 位随机字符")
    status: Mapped[str] = mapped_column(String(10), default="unused", comment="状态：unused 未用 / used 已用 / expired 过期 / revoked 已撤销")
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="发放人（admin）用户ID")
    used_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), comment="使用者用户ID（使用后写入）")
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, comment="过期时间，空表示不过期")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    used_at: Mapped[datetime | None] = mapped_column(DateTime, comment="使用时间（被注册时写入）")

    def __repr__(self) -> str:
        return f"<TeacherInviteCode {self.code} {self.status}>"


# --- homework ---
class Homework(Base):
    """作业表：老师布置。"""

    __tablename__ = "homework"
    __table_args__ = (
        {"comment": "作业表：老师布置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="作业ID")
    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"), nullable=False, comment="所属班级ID")
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="布置老师用户ID")
    title: Mapped[str] = mapped_column(String(100), nullable=False, comment="作业标题")
    description: Mapped[str | None] = mapped_column(Text, comment="作业描述/题目内容")
    subject: Mapped[str | None] = mapped_column(String(20), comment="科目：语文/数学/英语等")
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="截止时间，超过判定为迟交")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<Homework {self.title}>"


# --- homework_records ---
class HomeworkRecord(Base):
    """作业记录表：学生开始/提交打点，用于统计用时与状态。"""

    __tablename__ = "homework_records"
    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="uq_homework_student"),
        Index("ix_homework_records_student", "student_id"),
        {"comment": "作业记录表：学生开始/提交打点与用时统计"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    homework_id: Mapped[int] = mapped_column(Integer, ForeignKey("homework.id"), nullable=False, comment="作业ID")
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="学生用户ID")
    start_time: Mapped[datetime | None] = mapped_column(DateTime, comment="开始写作业时间，重复点击不覆盖")
    submit_time: Mapped[datetime | None] = mapped_column(DateTime, comment="提交时间")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, comment="用时（分钟）= 提交时间 - 开始时间；<1 分钟标记异常")
    status: Mapped[str | None] = mapped_column(String(10), comment="状态：not_started 未开始 / doing 进行中 / submitted 已提交 / late 迟交")
    file_url: Mapped[str | None] = mapped_column(String(255), comment="上传文件地址（jpg/png/pdf，≤10MB）")
    text_content: Mapped[str | None] = mapped_column(Text, comment="文本作答内容")
    points: Mapped[int] = mapped_column(Integer, default=0, comment="本次获得的积分（读 point_rules）")

    def __repr__(self) -> str:
        return f"<HomeworkRecord hw={self.homework_id} stu={self.student_id} {self.status}>"


# --- checkins ---
class Checkin(Base):
    """签到表：每日一次，同一天唯一。"""

    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("student_id", "checkin_date", name="uq_checkin_day"),
        {"comment": "签到表：每日一次，同一天唯一"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="签到ID")
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="学生用户ID")
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False, comment="签到日期")
    points: Mapped[int | None] = mapped_column(Integer, comment="本次获得积分（读 checkin_daily 规则）")
    streak: Mapped[int | None] = mapped_column(Integer, comment="连续签到天数，用于连续7天额外奖励")

    def __repr__(self) -> str:
        return f"<Checkin stu={self.student_id} {self.checkin_date}>"


# --- articles ---
class Article(Base):
    """文章表：课后阅读材料，teacher/admin 均可发布。"""

    __tablename__ = "articles"
    __table_args__ = (
        {"comment": "文章表：课后阅读材料，teacher/admin 均可发布"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="文章ID")
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="作者用户ID")
    created_role: Mapped[str | None] = mapped_column(String(10), comment="作者角色：teacher / admin")
    title: Mapped[str] = mapped_column(String(100), nullable=False, comment="文章标题")
    cover: Mapped[str | None] = mapped_column(String(255), comment="封面图地址")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="正文内容")
    file_url: Mapped[str | None] = mapped_column(String(255), comment="原始上传文件路径（迭代 v2.1）")
    file_name: Mapped[str | None] = mapped_column(String(255), comment="原始文件名（迭代 v2.1）")
    file_type: Mapped[str | None] = mapped_column(String(20), comment="原始文件类型：pdf / docx（迭代 v2.1）")
    status: Mapped[str] = mapped_column(String(10), default="published", comment="状态：published 已发布 / hidden 已隐藏（学生端仅见 published）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, comment="最后更新时间")

    def __repr__(self) -> str:
        return f"<Article {self.title}>"


# --- reading_records ---
class ReadingRecord(Base):
    """阅读记录表：按时长积分，需心跳防挂机校验。"""

    __tablename__ = "reading_records"
    __table_args__ = (
        UniqueConstraint("article_id", "student_id", "read_date", name="uq_reading_day"),
        {"comment": "阅读记录表：按时长积分，需心跳防挂机校验"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("articles.id"), nullable=False, comment="文章ID")
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="学生用户ID")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, comment="有效阅读时长（秒），仅累计通过心跳校验的时段")
    finished: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否读完（滚动到底标记）")
    points: Mapped[int] = mapped_column(Integer, default=0, comment="本次阅读获得积分")
    read_date: Mapped[date | None] = mapped_column(Date, comment="阅读日期（按日去重）")

    def __repr__(self) -> str:
        return f"<ReadingRecord art={self.article_id} stu={self.student_id}>"


# --- game_records ---
class GameRecord(Base):
    """游戏记录表：数独、成语接龙的成绩留痕。"""

    __tablename__ = "game_records"
    __table_args__ = (
        {"comment": "游戏记录表：数独、成语接龙的成绩留痕"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="记录ID")
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="学生用户ID")
    game_type: Mapped[str | None] = mapped_column(String(20), comment="游戏类型：sudoku 数独 / idiom 成语接龙")
    difficulty: Mapped[str | None] = mapped_column(String(10), comment="难度：数独用 easy/medium/hard")
    score: Mapped[int | None] = mapped_column(Integer, comment="游戏得分")
    points: Mapped[int | None] = mapped_column(Integer, comment="本次获得积分")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, comment="游戏时长（秒）")
    play_date: Mapped[date | None] = mapped_column(Date, comment="游戏日期（用于每日上限统计）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<GameRecord {self.game_type} stu={self.student_id}>"


# --- point_logs（核心） ---
class PointLog(Base):
    """积分流水表（核心）：所有积分变动必写，保证可追溯。"""

    __tablename__ = "point_logs"
    __table_args__ = (
        Index("ix_point_logs_student_date", "student_id", "log_date"),
        {"comment": "积分流水表（核心）：所有积分变动必写，保证可追溯"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="流水ID")
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="学生用户ID")
    type: Mapped[str] = mapped_column(String(20), nullable=False, comment="类型：checkin/homework/reading/game/consume（consume 为负数）")
    points: Mapped[int] = mapped_column(Integer, nullable=False, comment="积分数值，正为发放、负为扣减")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注说明")
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), comment="操作人ID（家长扣分时为家长ID）")
    log_date: Mapped[date] = mapped_column(Date, nullable=False, comment="积分归属日期，用于日上限统计")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<PointLog stu={self.student_id} {self.type} {self.points}>"


# --- parent_students ---
class ParentStudent(Base):
    """家长-学生关系表：一个家长可绑多个孩子。"""

    __tablename__ = "parent_students"
    __table_args__ = (
        UniqueConstraint("parent_id", "student_id", name="uq_parent_student"),
        {"comment": "家长-学生关系表：一个家长可绑多个孩子"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="关系ID")
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="家长用户ID")
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="学生用户ID")

    def __repr__(self) -> str:
        return f"<ParentStudent p={self.parent_id} s={self.student_id}>"


# --- point_rules（admin 可改，动态生效） ---
class PointRule(Base):
    """积分规则表：admin 可改，修改后立即生效。

    注意 `daily_limit` 的语义是「每天最多 N **次**」（PRD 6 总表），
    不是积分上限。游戏类规则的 20 表示「数独三档 + 成语接龙当日合计 20 分」。
    """

    __tablename__ = "point_rules"
    __table_args__ = (
        Index("ix_point_rules_key", "rule_key"),
        {"comment": "积分规则表：admin 可改，修改后立即生效（daily_limit 为每日次数上限）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="规则ID")
    rule_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="规则键，唯一且不可修改（如 checkin_daily）")
    rule_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="规则名称（展示用）")
    points: Mapped[int] = mapped_column(Integer, nullable=False, comment="每次发放的积分数")
    daily_limit: Mapped[int | None] = mapped_column(Integer, comment="每日次数上限；空表示不限。游戏规则为当日合计积分上限")
    extra_config: Mapped[str | None] = mapped_column(Text, comment="扩展配置（JSON 字符串），如 {\"single_article_limit\":10}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用；false 则不发放该积分")
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), comment="最后修改人（admin）ID")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="最后更新时间")

    def __repr__(self) -> str:
        return f"<PointRule {self.rule_key}={self.points}>"


# --- admin_logs ---
class AdminLog(Base):
    """管理员操作审计表：禁用、规则修改、文章删除等敏感操作留痕。"""

    __tablename__ = "admin_logs"
    __table_args__ = (
        {"comment": "管理员操作审计表：禁用、规则修改、文章删除等敏感操作留痕"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="日志ID")
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, comment="操作人（admin）用户ID")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作标识，如 user_disable / rule_update")
    target_type: Mapped[str | None] = mapped_column(String(30), comment="操作对象类型：user / point_rule / teacher_invite_code / article")
    target_id: Mapped[int | None] = mapped_column(Integer, comment="操作对象ID")
    detail: Mapped[str | None] = mapped_column(Text, comment="操作详情（JSON 或描述）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="操作时间")

    def __repr__(self) -> str:
        return f"<AdminLog {self.action}>"


# --- idiom_questions（决策 4：admin 后台导入） ---
class IdiomQuestion(Base):
    """成语接龙题库表：由 admin 后台导入，不内置于代码（决策 4）。"""

    __tablename__ = "idiom_questions"
    __table_args__ = (
        Index("ix_idiom_enabled", "enabled"),
        {"comment": "成语接龙题库表：由 admin 后台导入"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="题目ID")
    prompt: Mapped[str] = mapped_column(String(50), nullable=False, comment="题干（上一个成语的末字或题目文本）")
    answer: Mapped[str] = mapped_column(String(50), nullable=False, comment="正确答案")
    distractors: Mapped[str | None] = mapped_column(Text, comment="干扰项（JSON 数组），建议≥2个，不足时服务端随机补齐")
    difficulty: Mapped[str] = mapped_column(String(10), default="normal", comment="难度：normal / hard")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用；false 则学生端抽不到")
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), comment="导入人（admin）ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="导入时间")

    def __repr__(self) -> str:
        return f"<IdiomQuestion {self.prompt}->{self.answer}>"