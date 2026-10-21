"""枚举常量（PRD 4.1 注释中的取值）。

与 SQLAlchemy 模型分离，便于业务代码引用而无需引入 ORM 依赖。
"""

# --- 角色 ---
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_PARENT = "parent"
ALL_ROLES = (ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT, ROLE_PARENT)

# admin 不开放注册（PRD 5.1）
REGISTERABLE_ROLES = (ROLE_STUDENT, ROLE_TEACHER, ROLE_PARENT)

# --- 用户状态 ---
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"

# --- 老师邀请码状态 ---
INVITE_UNUSED = "unused"
INVITE_USED = "used"
INVITE_EXPIRED = "expired"
INVITE_REVOKED = "revoked"

# --- 作业状态 ---
HOMEWORK_NOT_STARTED = "not_started"
HOMEWORK_DOING = "doing"
HOMEWORK_SUBMITTED = "submitted"
HOMEWORK_LATE = "late"

# --- 积分流水类型 ---
POINT_TYPE_CHECKIN = "checkin"
POINT_TYPE_HOMEWORK = "homework"
POINT_TYPE_READING = "reading"
POINT_TYPE_GAME = "game"
POINT_TYPE_CONSUME = "consume"

# --- 文章状态 ---
ARTICLE_PUBLISHED = "published"
ARTICLE_HIDDEN = "hidden"