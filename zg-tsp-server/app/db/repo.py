"""仓储层 —— SQLAlchemy 实现。

方法签名与 P1 的内存版保持一致，因此 routers / services 无需改动。
所有方法均只读或返回 ORM 对象；写操作由调用方控制事务。
"""

from datetime import date, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AdminLog,
    Article,
    Checkin,
    Class,
    Homework,
    HomeworkRecord,
    HomeworkReviewRule,
    ParentStudent,
    PointLog,
    PointRule,
    ReadingRecord,
    TeacherInviteCode,
    User,
)


class Repo:
    """仓储。持有会话，由 FastAPI 依赖注入。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------- users ----------------

    def add_user(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()  # 回填自增主键
        return user

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_user_by_id_for_update(self, user_id: int) -> User | None:
        """取用户并加行锁（SELECT ... FOR UPDATE）。

        发放/回扣积分时锁住用户行，避免同一学生的并发积分变动互相覆盖
        （两个会话都读到同一个旧余额，后写的把先写的覆盖掉）。

        带 `populate_existing`：加锁读若命中 identity map 中已缓存的对象，
        默认**不会**刷新其属性（读到的是加锁前的旧余额），行锁就白加了。
        强制用本次加锁读到的最新值覆盖 —— SQLAlchemy 官方对
        `with_for_update()` 的推荐用法。
        """
        return self.db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def get_user_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def list_users_by_ids(self, user_ids: list[int]) -> dict[int, User]:
        """批量取用户，返回 {user_id: User}（阅读记录等场景要展示学生姓名）。"""
        if not user_ids:
            return {}
        users = self.db.scalars(select(User).where(User.id.in_(user_ids)))
        return {u.id: u for u in users}

    def list_users(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.id)))

    def count_users(self) -> int:
        return self.db.scalar(select(func.count()).select_from(User)) or 0

    def list_users_paged(
        self,
        role: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[User], int]:
        """用户分页列表（角色/状态筛选 + 关键词搜索）。返回 (当前页, 总数)。

        keyword 同时匹配 username 与 nickname（PRD 5.8.2「搜索」）。
        """
        stmt: Select = select(User)
        count_stmt = select(func.count()).select_from(User)

        conditions = []
        if role:
            conditions.append(User.role == role)
        if status:
            conditions.append(User.status == status)
        if keyword:
            like = f"%{keyword}%"
            conditions.append(or_(User.username.like(like), User.nickname.like(like)))

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = self.db.scalar(count_stmt) or 0
        stmt = stmt.order_by(User.id).offset((page - 1) * size).limit(size)
        return list(self.db.scalars(stmt)), total

    # ---------------- 审计日志 ----------------

    def add_admin_log(
        self,
        admin_id: int,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        detail: str | None = None,
    ) -> AdminLog:
        log = AdminLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
        self.db.add(log)
        self.db.flush()
        return log

    # ---------------- 统计（PRD 5.8.5） ----------------

    def count_by_role(self, role: str) -> int:
        return self.db.scalar(
            select(func.count()).select_from(User).where(User.role == role)
        ) or 0

    def count_active_users(self) -> int:
        return self.db.scalar(
            select(func.count()).select_from(User).where(User.status == "active")
        ) or 0

    def count_classes(self) -> int:
        return self.db.scalar(select(func.count()).select_from(Class)) or 0

    def count_homework(self) -> int:
        return self.db.scalar(select(func.count()).select_from(Homework)) or 0

    def sum_points(self) -> int:
        return self.db.scalar(
            select(func.coalesce(func.sum(User.total_points), 0)).where(User.role == "student")
        ) or 0

    def count_point_logs(self) -> int:
        return self.db.scalar(select(func.count()).select_from(PointLog)) or 0

    def list_classes_paged(self, page: int = 1, size: int = 20) -> tuple[list[Class], int]:
        total = self.count_classes()
        stmt = (
            select(Class)
            .order_by(Class.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(stmt)), total

    def count_students_by_class(self) -> dict[int, int]:
        """各班级学生数，返回 {class_id: count}。"""
        rows = self.db.execute(
            select(User.class_id, func.count(User.id))
            .where(User.class_id.isnot(None))
            .group_by(User.class_id)
        ).all()
        return {cid: cnt for cid, cnt in rows}

    def add_class(self, klass: Class) -> Class:
        self.db.add(klass)
        self.db.flush()
        return klass

    def get_class_by_id(self, class_id: int) -> Class | None:
        return self.db.get(Class, class_id)

    def get_class_by_invite_code(self, invite_code: str) -> Class | None:
        return self.db.scalar(select(Class).where(Class.invite_code == invite_code))

    def get_class_for_update(self, class_id: int) -> Class | None:
        return self.db.scalar(select(Class).where(Class.id == class_id).with_for_update().execution_options(populate_existing=True))

    def get_class_by_code_for_update(self, code: str) -> Class | None:
        return self.db.scalar(select(Class).where(Class.invite_code == code).with_for_update().execution_options(populate_existing=True))

    def list_classes_by_teacher(self, teacher_id: int) -> list[Class]:
        return list(self.db.scalars(select(Class).where(Class.teacher_id == teacher_id).order_by(Class.id)))

    def list_students_in_class(self, class_id: int) -> list[User]:
        """班级内学生列表（决策 3：学生只属一个班级）。"""
        return list(
            self.db.scalars(
                select(User).where(User.class_id == class_id).order_by(User.id)
            )
        )

    # ---------------- 作业（PRD 5.3） ----------------

    def add_homework(self, hw: Homework) -> Homework:
        self.db.add(hw)
        self.db.flush()
        return hw

    def get_homework_by_id(self, homework_id: int) -> Homework | None:
        return self.db.get(Homework, homework_id)

    def get_homework_for_update(self, homework_id: int) -> Homework | None:
        return self.db.scalar(
            select(Homework).where(Homework.id == homework_id)
            .with_for_update().execution_options(populate_existing=True)
        )

    def list_homework_paged(
        self,
        class_id: int,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Homework], int]:
        total = self.db.scalar(
            select(func.count()).select_from(Homework).where(Homework.class_id == class_id)
        ) or 0
        stmt = (
            select(Homework)
            .where(Homework.class_id == class_id)
            .order_by(Homework.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(self.db.scalars(stmt)), total

    def list_homework_today(self, class_id: int, day: date) -> list[Homework]:
        """学生端「今日作业」：当天截止的作业。"""
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        return list(
            self.db.scalars(
                select(Homework)
                .where(Homework.class_id == class_id, Homework.deadline >= start, Homework.deadline <= end)
                .order_by(Homework.deadline)
            )
        )

    def list_my_submitted_homework(
        self, student_id: int, class_id: int, page: int, size: int
    ) -> tuple[list, int]:
        base = (
            select(Homework, HomeworkRecord)
            .join(HomeworkRecord, HomeworkRecord.homework_id == Homework.id)
            .where(
                Homework.class_id == class_id,
                HomeworkRecord.student_id == student_id,
                HomeworkRecord.submit_time.is_not(None),
            )
        )
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.db.execute(
            base.order_by(HomeworkRecord.submit_time.desc(), HomeworkRecord.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        return rows, total

    def add_homework_record(self, record: HomeworkRecord) -> HomeworkRecord:
        self.db.add(record)
        self.db.flush()
        return record

    def get_homework_record(
        self, homework_id: int, student_id: int
    ) -> HomeworkRecord | None:
        return self.db.scalar(
            select(HomeworkRecord).where(
                HomeworkRecord.homework_id == homework_id,
                HomeworkRecord.student_id == student_id,
            )
        )

    def get_homework_record_for_update(
        self, homework_id: int, student_id: int
    ) -> HomeworkRecord | None:
        """取记录并加行锁（SELECT ... FOR UPDATE）。

        批改作业时用，防止两个老师同时批改同一份导致积分重复发放
        （PRD 5.3）。仅 MySQL 生效。
        """
        return self.db.scalar(
            select(HomeworkRecord)
            .where(
                HomeworkRecord.homework_id == homework_id,
                HomeworkRecord.student_id == student_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )

    def list_homework_records_for_update(self, homework_id: int) -> list[HomeworkRecord]:
        return list(self.db.scalars(
            select(HomeworkRecord).where(HomeworkRecord.homework_id == homework_id)
            .order_by(HomeworkRecord.id).with_for_update()
            .execution_options(populate_existing=True)
        ))

    def list_homework_records(self, homework_id: int) -> list[HomeworkRecord]:
        return list(
            self.db.scalars(
                select(HomeworkRecord)
                .where(HomeworkRecord.homework_id == homework_id)
                .order_by(HomeworkRecord.id)
            )
        )

    def count_submitted_records(self, homework_id: int) -> int:
        """已提交（含迟交）人数 —— 用于「仅无人提交时可删除」判定。"""
        return self.db.scalar(
            select(func.count()).select_from(HomeworkRecord).where(
                HomeworkRecord.homework_id == homework_id,
                HomeworkRecord.submit_time.isnot(None),
            )
        ) or 0

    def list_pending_reviews(
        self, teacher_id: int, page: int = 1, size: int = 20
    ) -> tuple[list[dict], int]:
        """待批改列表：该老师所有班级的「已提交但未批改」记录（PRD 5.3）。

        返回 (当前页行, 总数)。每行含学生名、作业标题、提交信息与异常标记。
        """
        base = (
            select(HomeworkRecord, Homework, User)
            .join(Homework, Homework.id == HomeworkRecord.homework_id)
            .join(User, User.id == HomeworkRecord.student_id)
            .join(Class, Class.id == Homework.class_id)
            .where(
                Class.teacher_id == teacher_id,
                HomeworkRecord.submit_time.isnot(None),
                HomeworkRecord.reviewed_at.is_(None),
            )
        )
        count_stmt = (
            select(func.count())
            .select_from(HomeworkRecord)
            .join(Homework, Homework.id == HomeworkRecord.homework_id)
            .join(Class, Class.id == Homework.class_id)
            .where(
                Class.teacher_id == teacher_id,
                HomeworkRecord.submit_time.isnot(None),
                HomeworkRecord.reviewed_at.is_(None),
            )
        )
        total = self.db.scalar(count_stmt) or 0
        stmt = (
            base.order_by(HomeworkRecord.submit_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = []
        for rec, hw, stu in self.db.execute(stmt).all():
            rows.append({
                "homework_id": hw.id,
                "homework_title": hw.title,
                "student_id": stu.id,
                "student_name": stu.nickname or stu.username,
                "username": stu.username,
                "submit_time": rec.submit_time.isoformat() if rec.submit_time else None,
                "duration_minutes": rec.duration_minutes,
                "file_url": rec.file_url,
                "text_content": rec.text_content,
                # 用时 <1 分钟标记异常（PRD 5.3）
                "suspicious": bool(
                    rec.duration_minutes is not None and rec.duration_minutes < 1
                ),
            })
        return rows, total

    # ---------------- 作业批改档位（PRD 5.3） ----------------

    def add_review_rule(self, rule: HomeworkReviewRule) -> HomeworkReviewRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_review_rule_by_min_score(self, min_score: int) -> HomeworkReviewRule | None:
        return self.db.scalar(
            select(HomeworkReviewRule).where(HomeworkReviewRule.min_score == min_score)
        )

    def list_review_rules(self) -> list[HomeworkReviewRule]:
        """全部档位（按分数下限从高到低）。"""
        return list(
            self.db.scalars(
                select(HomeworkReviewRule).order_by(HomeworkReviewRule.min_score.desc())
            )
        )

    def get_review_rule_by_id(self, rule_id: int) -> HomeworkReviewRule | None:
        return self.db.get(HomeworkReviewRule, rule_id)

    def match_review_points(self, score: int) -> int:
        """按分数匹配档位，返回该档积分；无匹配返回 0。

        取所有 enabled 且 min_score <= score 的档位中 min_score 最大的一档。
        """
        rule = self.db.scalar(
            select(HomeworkReviewRule)
            .where(
                HomeworkReviewRule.enabled.is_(True),
                HomeworkReviewRule.min_score <= score,
            )
            .order_by(HomeworkReviewRule.min_score.desc())
            .limit(1)
        )
        return rule.points if rule else 0

    # ---------------- 签到（PRD 5.4） ----------------

    def add_checkin(self, checkin: Checkin) -> Checkin:
        self.db.add(checkin)
        self.db.flush()
        return checkin

    def get_checkin(self, student_id: int, day: date, *, for_update: bool = False) -> Checkin | None:
        stmt = select(Checkin).where(Checkin.student_id == student_id, Checkin.checkin_date == day)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.db.scalar(stmt)

    def list_checkins_desc(self, student_id: int, limit: int = 60, *, for_update: bool = False) -> list[Checkin]:
        """最近的签到记录（倒序），用于计算连续签到天数。"""
        stmt = (select(Checkin).where(Checkin.student_id == student_id)
                .order_by(Checkin.checkin_date.desc()).limit(limit))
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return list(self.db.scalars(stmt))

    # ---------------- 排行榜（PRD 5.4） ----------------

    def rank_day(
        self, day: date, page: int = 1, size: int = 50
    ) -> tuple[list[tuple[int, int]], int]:
        """今日榜：按当日 PointLog 正向积分聚合。

        返回 ([(student_id, points), ...], 参与人数)。
        同分按「当日首次得分时间」先后 —— 先达成者靠前（PRD 5.4）。
        排除 admin 角色（PRD 5.4、第 8 节）。
        """
        # 只统计学生：admin 不参与业务、不计积分（PRD 8）
        pts = func.sum(PointLog.points)
        first_id = func.min(PointLog.id)
        base = (
            select(PointLog.student_id, pts, first_id)
            .join(User, User.id == PointLog.student_id)
            .where(
                PointLog.log_date == day,
                PointLog.points > 0,
                User.role == "student",
            )
            .group_by(PointLog.student_id)
        )
        total = self.db.scalar(
            select(func.count()).select_from(base.subquery())
        ) or 0

        # first_id 单调递增，与达成时间先后一致（PRD 5.4）
        rows = self.db.execute(
            select(PointLog.student_id, pts, first_id)
            .join(User, User.id == PointLog.student_id)
            .where(
                PointLog.log_date == day,
                PointLog.points > 0,
                User.role == "student",
            )
            .group_by(PointLog.student_id)
            .order_by(pts.desc(), first_id.asc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        return [(r[0], r[1]) for r in rows], total

    def rank_total(
        self, page: int = 1, size: int = 50
    ) -> tuple[list[tuple[int, int]], int]:
        """总榜：按 users.total_points 排序，排除 admin（PRD 5.4、第 8 节）。

        同分按「首次获得积分的时间」先后 —— 用最早一条 point_logs.id 近似。
        """
        # 只取学生：admin 不参与业务、不计积分（PRD 8）
        candidates = select(User.id, User.total_points).where(
            User.role == "student"
        )
        total = self.db.scalar(
            select(func.count()).select_from(candidates.subquery())
        ) or 0

        first_earn = (
            select(PointLog.student_id.label("sid"), func.min(PointLog.id).label("first_id"))
            .where(PointLog.points > 0)
            .group_by(PointLog.student_id)
            .subquery()
        )
        rows = self.db.execute(
            select(User.id, User.total_points)
            .outerjoin(first_earn, first_earn.c.sid == User.id)
            .where(User.role == "student")
            .order_by(User.total_points.desc(), first_earn.c.first_id.asc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        return [(r[0], r[1]) for r in rows], total

    def rank_position(self, student_id: int, day: date | None = None) -> int:
        """某学生的名次（1 起）。day 传 None 表示总榜。"""
        if day is None:
            rows, _ = self.rank_total(page=1, size=10**6)
        else:
            rows, _ = self.rank_day(day=day, page=1, size=10**6)
        for idx, (sid, _) in enumerate(rows, start=1):
            if sid == student_id:
                return idx
        return 0

    # ---------------- 家长-学生（PRD 5.7） ----------------

    def get_user_by_bind_code(self, bind_code: str) -> User | None:
        """按学生绑定码查学生（家长绑定用）。"""
        return self.db.scalar(
            select(User).where(
                User.bind_code == bind_code.strip().upper(),
                User.role == "student",
            )
        )

    def get_student_by_code_for_update(self, code: str) -> User | None:
        return self.db.scalar(select(User).where(
            User.bind_code == code.strip().upper(), User.role == "student"
        ).with_for_update().execution_options(populate_existing=True))

    def add_parent_student(self, rel: ParentStudent) -> ParentStudent:
        self.db.add(rel)
        self.db.flush()
        return rel

    def get_parent_student(self, parent_id: int, student_id: int) -> ParentStudent | None:
        return self.db.scalar(
            select(ParentStudent).where(
                ParentStudent.parent_id == parent_id,
                ParentStudent.student_id == student_id,
            )
        )

    def get_parent_student_for_update(self, parent_id: int, student_id: int) -> ParentStudent | None:
        return self.db.scalar(select(ParentStudent).where(
            ParentStudent.parent_id == parent_id, ParentStudent.student_id == student_id
        ).with_for_update().execution_options(populate_existing=True))

    def list_children(self, parent_id: int) -> list[User]:
        """某家长绑定的孩子列表（PRD 5.7：一个家长可绑多个）。"""
        return list(
            self.db.scalars(
                select(User)
                .join(ParentStudent, ParentStudent.student_id == User.id)
                .where(ParentStudent.parent_id == parent_id)
                .order_by(ParentStudent.id)
            )
        )

    # ---------------- 文章与阅读（PRD 5.5） ----------------

    def add_article(self, art: Article) -> Article:
        self.db.add(art)
        self.db.flush()
        return art

    def get_article_by_id(self, article_id: int, *, for_update: bool = False) -> Article | None:
        stmt = select(Article).where(Article.id == article_id, Article.deleted_at.is_(None))
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.db.scalar(stmt)

    def list_articles_paged(
        self,
        status: str | None = None,
        author_id: int | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Article], int]:
        """文章分页列表。学生端只传 status='published'。"""
        stmt = select(Article)
        count_stmt = select(func.count()).select_from(Article)

        conditions = [Article.deleted_at.is_(None)]
        if status:
            conditions.append(Article.status == status)
        if author_id:
            conditions.append(Article.author_id == author_id)
        if keyword:
            like = f"%{keyword}%"
            conditions.append(or_(Article.title.like(like), Article.content.like(like)))
        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = self.db.scalar(count_stmt) or 0
        stmt = stmt.order_by(Article.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.scalars(stmt)), total

    def add_reading_record(self, rec: ReadingRecord) -> ReadingRecord:
        self.db.add(rec)
        self.db.flush()
        return rec

    def get_reading_record(
        self, article_id: int, student_id: int, day: date, *, for_update: bool = False
    ) -> ReadingRecord | None:
        """当天的阅读记录（PRD 4.1：UNIQUE(article_id, student_id, read_date)）。"""
        stmt = select(ReadingRecord).where(
            ReadingRecord.article_id == article_id,
            ReadingRecord.student_id == student_id,
            ReadingRecord.read_date == day,
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.db.scalar(stmt)

    def list_reading_records(self, article_id: int) -> list[ReadingRecord]:
        return list(
            self.db.scalars(
                select(ReadingRecord)
                .where(ReadingRecord.article_id == article_id)
                .order_by(ReadingRecord.id)
            )
        )

    def article_read_stats(self, article_id: int) -> dict:
        """阅读统计：阅读人数、完成数、总时长（PRD 5.8.4）。"""
        row = self.db.execute(
            select(
                func.count(ReadingRecord.id).label("readers"),
                func.coalesce(func.sum(ReadingRecord.duration_seconds), 0).label("seconds"),
            ).where(ReadingRecord.article_id == article_id)
        ).one()
        finished = self.db.scalar(
            select(func.count()).select_from(ReadingRecord).where(
                ReadingRecord.article_id == article_id,
                ReadingRecord.finished.is_(True),
            )
        ) or 0
        return {
            "reader_count": row.readers or 0,
            "finished_count": finished,
            "total_duration_seconds": int(row.seconds or 0),
        }

    # ---------------- 老师邀请码 ----------------

    def add_invite_code(
        self,
        code: str,
        created_by: int,
        expire_at: datetime | None = None,
    ) -> TeacherInviteCode:
        invite = TeacherInviteCode(
            code=code,
            created_by=created_by,
            expire_at=expire_at,
        )
        self.db.add(invite)
        self.db.flush()
        return invite

    def get_invite_by_code(self, code: str) -> TeacherInviteCode | None:
        return self.db.scalar(select(TeacherInviteCode).where(TeacherInviteCode.code == code))

    def get_invite_for_update(self, *, code: str | None = None, invite_id: int | None = None) -> TeacherInviteCode | None:
        condition = TeacherInviteCode.code == code if code is not None else TeacherInviteCode.id == invite_id
        return self.db.scalar(select(TeacherInviteCode).where(condition).with_for_update().execution_options(populate_existing=True))

    def list_invite_codes_paged(
        self,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[TeacherInviteCode], int]:
        """邀请码分页列表（可按状态筛选）。返回 (当前页, 总数)。"""
        stmt: Select = select(TeacherInviteCode)
        count_stmt = select(func.count()).select_from(TeacherInviteCode)
        if status:
            stmt = stmt.where(TeacherInviteCode.status == status)
            count_stmt = count_stmt.where(TeacherInviteCode.status == status)

        total = self.db.scalar(count_stmt) or 0
        stmt = stmt.order_by(TeacherInviteCode.id.desc()).offset((page - 1) * size).limit(size)
        return list(self.db.scalars(stmt)), total

    # ---------------- 积分规则 ----------------

    def add_point_rule(self, rule: PointRule) -> PointRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_rule_by_key(self, rule_key: str) -> PointRule | None:
        return self.db.scalar(select(PointRule).where(PointRule.rule_key == rule_key))

    def list_point_rules(self) -> list[PointRule]:
        return list(self.db.scalars(select(PointRule).order_by(PointRule.id)))
