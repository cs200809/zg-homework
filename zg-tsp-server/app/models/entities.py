"""SQLAlchemy 模型 —— 对应 PRD 4.1 建表 SQL。

命名、类型、约束均按 PRD 4.1；索引按 PRD 4.1 末尾要求。

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有表的基类。"""


# --- users ---
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(30))
    avatar: Mapped[str | None] = mapped_column(String(255))
    class_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("classes.id"))
    bind_code: Mapped[str | None] = mapped_column(String(8))
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="active")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_users_class_id", "class_id"),)

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role})>"


# --- classes ---
class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Class {self.name}>"


# --- teacher_invite_codes ---
class TeacherInviteCode(Base):
    __tablename__ = "teacher_invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="unused")
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    used_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    expire_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    used_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("ix_invite_code_status", "code", "status"),)

    def __repr__(self) -> str:
        return f"<TeacherInviteCode {self.code} {self.status}>"


# --- homework ---
class Homework(Base):
    __tablename__ = "homework"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(Integer, ForeignKey("classes.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(20))
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Homework {self.title}>"


# --- homework_records ---
class HomeworkRecord(Base):
    __tablename__ = "homework_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    homework_id: Mapped[int] = mapped_column(Integer, ForeignKey("homework.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    submit_time: Mapped[datetime | None] = mapped_column(DateTime)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(10))
    file_url: Mapped[str | None] = mapped_column(String(255))
    text_content: Mapped[str | None] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="uq_homework_student"),
        Index("ix_homework_records_student", "student_id"),
    )

    def __repr__(self) -> str:
        return f"<HomeworkRecord hw={self.homework_id} stu={self.student_id} {self.status}>"


# --- checkins ---
class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    points: Mapped[int | None] = mapped_column(Integer)
    streak: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("student_id", "checkin_date", name="uq_checkin_day"),)

    def __repr__(self) -> str:
        return f"<Checkin stu={self.student_id} {self.checkin_date}>"


# --- articles ---
class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_role: Mapped[str | None] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    cover: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return f"<Article {self.title}>"


# --- reading_records ---
class ReadingRecord(Base):
    __tablename__ = "reading_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("articles.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    points: Mapped[int] = mapped_column(Integer, default=0)
    read_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("article_id", "student_id", "read_date", name="uq_reading_day"),
    )

    def __repr__(self) -> str:
        return f"<ReadingRecord art={self.article_id} stu={self.student_id}>"


# --- game_records ---
class GameRecord(Base):
    __tablename__ = "game_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    game_type: Mapped[str | None] = mapped_column(String(20))
    difficulty: Mapped[str | None] = mapped_column(String(10))
    score: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    play_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<GameRecord {self.game_type} stu={self.student_id}>"


# --- point_logs（核心） ---
class PointLog(Base):
    __tablename__ = "point_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255))
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_point_logs_student_date", "student_id", "log_date"),)

    def __repr__(self) -> str:
        return f"<PointLog stu={self.student_id} {self.type} {self.points}>"


# --- parent_students ---
class ParentStudent(Base):
    __tablename__ = "parent_students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("parent_id", "student_id", name="uq_parent_student"),
    )

    def __repr__(self) -> str:
        return f"<ParentStudent p={self.parent_id} s={self.student_id}>"


# --- point_rules（admin 可改，动态生效） ---
class PointRule(Base):
    __tablename__ = "point_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(50), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_limit: Mapped[int | None] = mapped_column(Integer)
    extra_config: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_point_rules_key", "rule_key"),)

    def __repr__(self) -> str:
        return f"<PointRule {self.rule_key}={self.points}>"


# --- admin_logs ---
class AdminLog(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AdminLog {self.action}>"


# --- idiom_questions（决策 4：admin 后台导入） ---
class IdiomQuestion(Base):
    __tablename__ = "idiom_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt: Mapped[str] = mapped_column(String(50), nullable=False)
    answer: Mapped[str] = mapped_column(String(50), nullable=False)
    distractors: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(10), default="normal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_idiom_enabled", "enabled"),)

    def __repr__(self) -> str:
        return f"<IdiomQuestion {self.prompt}->{self.answer}>"