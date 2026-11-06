/** 家长端与 admin 端接口（PRD 5.7、5.8）。 */

import { post } from './client'
import type { PageResult } from './classes'
import type {
  AdminUser,
  Article,
  Child,
  ConsumeItem,
  HomeworkReviewRule,
  InviteCode,
  PointLog,
  PointRule,
  Role,
  StatsOverview,
} from './types'

// ---------- 家长（PRD 5.7） ----------
export const parentApi = {
  bind: (bindCode: string) =>
    post<{
      student_id: number
      username: string
      nickname: string | null
      total_points: number
    }>('/parent/bind', { bind_code: bindCode }),

  children: () => post<{ list: Child[]; total: number }>('/parent/children'),

  childPoints: (studentId: number, page = 1, size = 20) =>
    post<{
      student: { id: number; nickname: string | null; total_points: number }
      summary: {
        total_points: number
        gained_today: number
        total_gained: number
        total_consumed: number
      }
      list: PointLog[]
      total: number
      page: number
      size: number
    }>('/parent/child-points', { student_id: studentId, page, size }),

  consume: (studentId: number, item: string, points: number, remark?: string) =>
    post<{ student_id: number; item: string; points: number; total_points: number }>(
      '/parent/consume',
      { student_id: studentId, item, points, ...(remark ? { remark } : {}) },
    ),

  consumeItems: () => post<{ list: ConsumeItem[] }>('/parent/consume-items'),

  unbind: (studentId: number) =>
    post<{ unbound_student_id: number }>('/parent/unbind', { student_id: studentId }),
}

// ---------- admin：邀请码（PRD 5.8.1） ----------
export const inviteApi = {
  create: (count: number, expireDays = 7) =>
    post<{ codes: string[]; count: number; expire_at: string }>('/admin/invite/create', {
      count,
      expire_days: expireDays,
    }),

  list: (page = 1, size = 20, status?: string) =>
    post<PageResult<InviteCode>>('/admin/invite/list', {
      page,
      size,
      ...(status ? { status } : {}),
    }),

  revoke: (codeId: number) =>
    post<{ code_id: number; status: string }>('/admin/invite/revoke', { code_id: codeId }),
}

// ---------- admin：用户（PRD 5.8.2） ----------
export const userApi = {
  list: (params: { page?: number; size?: number; role?: Role; status?: string; keyword?: string } = {}) =>
    post<PageResult<AdminUser>>('/admin/users/list', params as Record<string, unknown>),

  detail: (userId: number) =>
    post<{ user: AdminUser }>('/admin/users/detail', { user_id: userId }),

  disable: (userId: number) =>
    post<{ user_id: number; status: string }>('/admin/users/disable', { user_id: userId }),

  enable: (userId: number) =>
    post<{ user_id: number; status: string }>('/admin/users/enable', { user_id: userId }),

  resetPassword: (userId: number) =>
    post<{ user_id: number; temp_password: string }>('/admin/users/reset-password', {
      user_id: userId,
    }),
}

// ---------- admin：积分规则（PRD 5.8.3） ----------
export const ruleApi = {
  list: () => post<{ list: PointRule[]; total: number }>('/admin/rules/list'),

  detail: (ruleKey: string) =>
    post<{ rule: PointRule }>('/admin/rules/detail', { rule_key: ruleKey }),

  update: (params: {
    rule_key: string
    points?: number
    daily_limit?: number | null
    extra_config?: string | null
    enabled?: boolean
  }) => post<{ rule: PointRule }>('/admin/rules/update', params as Record<string, unknown>),

  batchUpdate: (rules: Record<string, unknown>[]) =>
    post<{ updated: PointRule[]; count: number }>('/admin/rules/batch-update', { rules }),
}

// ---------- admin：文章（PRD 5.8.4） ----------
export const adminArticleApi = {
  list: (
    params: {
      page?: number
      size?: number
      author_role?: Role
      author_id?: number
      status?: string
      keyword?: string
    } = {},
  ) => post<PageResult<Article>>('/admin/articles/list', params as Record<string, unknown>),
}

// ---------- admin：统计（PRD 5.8.5） ----------
export const statsApi = {
  overview: () => post<StatsOverview>('/admin/stats/overview'),

  classes: (page = 1, size = 20) =>
    post<
      PageResult<{
        id: number
        name: string
        invite_code: string
        teacher_name: string | null
        student_count: number
        created_at: string
      }>
    >('/admin/classes/list', { page, size }),
}

// ---------- admin：作业批改档位（PRD 5.3） ----------
/** 作业批改档位配置（admin）。沿用本文件混放 admin 接口的现状。 */
export const reviewRuleApi = {
  list: () =>
    post<{ list: HomeworkReviewRule[]; total: number }>('/admin/homework-review-rules/list'),

  create: (minScore: number, points: number) =>
    post<{ rule: HomeworkReviewRule }>('/admin/homework-review-rules/create', {
      min_score: minScore,
      points,
    }),

  update: (id: number, fields: { points?: number; enabled?: boolean }) =>
    post<{ rule: HomeworkReviewRule }>('/admin/homework-review-rules/update', { id, ...fields }),
}
