/**
 * 服务端数据类型定义。
 *
 * 与 zg-tsp-server 的响应结构一一对应（PRD 第 7 节接口清单），
 * 契约变更时以服务端为准。
 */

export type Role = 'admin' | 'teacher' | 'student' | 'parent'

export interface UserInfo {
  id: number
  username: string
  role: Role
  nickname: string | null
  avatar: string | null
  class_id: number | null
  bind_code: string | null
  total_points: number
  must_change_password: boolean
}

export interface LoginResult {
  token: string
  expire_at: number
  user: UserInfo
  must_change_password: boolean
}

// ---------- 班级 ----------
export interface ClassInfo {
  id: number
  name: string
  invite_code: string
  teacher_id: number
  created_at: string | null
  student_count: number | null
}

export interface ClassStudent {
  id: number
  username: string
  nickname: string | null
  total_points: number
  created_at: string | null
}

// ---------- 作业 ----------
export type HomeworkStatus = 'not_started' | 'doing' | 'submitted' | 'late'

export interface Homework {
  id: number
  class_id: number
  teacher_id: number
  title: string
  description: string | null
  subject: string | null
  deadline: string
  created_at: string | null
  my_status?: HomeworkStatus
  my_points?: number
  /** 学生视角：自己的作答记录（/homework/detail 返回） */
  my_record?: HomeworkRecord | null
}

export interface HomeworkRecord {
  id: number
  homework_id: number
  student_id: number
  start_time: string | null
  submit_time: string | null
  duration_minutes: number | null
  status: HomeworkStatus
  file_url: string | null
  text_content: string | null
  points: number
  suspicious: boolean
  /** 老师批改分数 0–100；null 表示未批改 */
  review_score?: number | null
  /** 老师评语 */
  review_comment?: string | null
  /** 批改时间 */
  reviewed_at?: string | null
  /** 实际已发放的批改积分 */
  review_points?: number
}

export interface HomeworkRecordRow {
  student_id: number
  username: string
  nickname: string | null
  status: HomeworkStatus
  points: number
  start_time?: string | null
  submit_time?: string | null
  duration_minutes?: number | null
  file_url?: string | null
  text_content?: string | null
  suspicious?: boolean
  /** 老师批改分数 0–100；null/undefined 表示未批改 */
  review_score?: number | null
  /** 老师评语 */
  review_comment?: string | null
  /** 批改时间 */
  reviewed_at?: string | null
  /** 实际已发放的批改积分 */
  review_points?: number
}

/** 作业批改档位（admin 可配） */
export interface HomeworkReviewRule {
  id: number
  /** 档位分数下限（含） */
  min_score: number
  /** 该档位发放的积分 */
  points: number
  enabled: boolean
  updated_at: string | null
}

/** 待批改列表行 */
export interface PendingReviewRow {
  homework_id: number
  homework_title: string
  student_id: number
  student_name: string
  username: string
  submit_time: string | null
  duration_minutes: number | null
  file_url: string | null
  text_content: string | null
  /** 用时 <1 分钟标记异常 */
  suspicious: boolean
}

// ---------- 文章 ----------
export type ArticleStatus = 'published' | 'hidden'

export interface Article {
  id: number
  author_id: number
  created_role: Role
  title: string
  cover: string | null
  content?: string
  status: ArticleStatus
  created_at: string | null
  /** 原始上传文件路径（迭代 v2.1） */
  file_url?: string | null
  /** 原始文件名（迭代 v2.1） */
  file_name?: string | null
  /** 原始文件类型 pdf / docx（迭代 v2.1） */
  file_type?: string | null
  my_record?: { duration_seconds: number; finished: boolean; points: number } | null
}

/** 导出 PDF 结果（迭代 v2.1） */
export interface ExportPdfResult {
  file_url: string
  file_name: string
  size_bytes: number
}

export interface ArticleStats {
  reader_count: number
  finished_count: number
  total_duration_seconds: number
}

// ---------- 积分 ----------
export type PointType = 'checkin' | 'homework' | 'reading' | 'game' | 'consume' | 'review'

export interface PointLog {
  id: number
  type: PointType
  points: number
  remark: string | null
  operator_id: number | null
  log_date: string | null
  created_at: string | null
}

export interface RankItem {
  rank: number
  user_id: number
  username: string | null
  nickname: string | null
  points: number
}

// ---------- 家长 ----------
export interface Child {
  student_id: number
  username: string
  nickname: string | null
  avatar: string | null
  class_id: number | null
  total_points: number
}

export interface ConsumeItem {
  key: string
  name: string
  points: number
}

// ---------- 游戏 ----------
export interface SudokuBoard {
  puzzle_id: string
  difficulty: string
  board: number[][]
  holes: number
}

export interface IdiomQuestionView {
  question_id: number
  prompt: string
  options: string[]
}

export interface GameRecord {
  id: number
  game_type: 'sudoku' | 'idiom'
  difficulty: string | null
  points: number | null
  duration_seconds: number | null
  play_date: string | null
  created_at: string | null
}

// ---------- admin ----------
export interface AdminUser {
  id: number
  username: string
  role: Role
  nickname: string | null
  avatar: string | null
  class_id: number | null
  bind_code: string | null
  total_points: number
  status: 'active' | 'disabled'
  must_change_password: boolean
  created_at: string
}

export interface InviteCode {
  id: number
  code: string
  status: 'unused' | 'used' | 'expired' | 'revoked'
  created_by: number
  used_by_user_id: number | null
  expire_at: string | null
  created_at: string
  used_at: string | null
}

export interface PointRule {
  id: number
  rule_key: string
  rule_name: string
  points: number
  daily_limit: number | null
  extra_config: string | null
  enabled: boolean
  updated_at: string | null
}

export interface StatsOverview {
  user_count: number
  active_user_count: number
  admin_count: number
  teacher_count: number
  student_count: number
  parent_count: number
  class_count: number
  homework_count: number
  point_total: number
  point_log_count: number
}