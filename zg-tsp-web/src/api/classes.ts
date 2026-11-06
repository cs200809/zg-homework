/** 班级与作业接口（PRD 5.2、5.3）。 */

import { client, post } from './client'
import type {
  ClassInfo,
  ClassStudent,
  Homework,
  HomeworkRecord,
  HomeworkRecordRow,
  PendingReviewRow,
} from './types'

export interface PageResult<T> {
  list: T[]
  total: number
  page: number
  size: number
}

export const classApi = {
  create: (name: string) => post<{ class: ClassInfo }>('/classes/create', { name }),

  join: (inviteCode: string) =>
    post<{ class: ClassInfo }>('/classes/join', { invite_code: inviteCode }),

  my: () => post<{ role: string; classes: ClassInfo[] }>('/classes/my'),

  students: (classId: number) =>
    post<{ class: ClassInfo; students: ClassStudent[] }>('/classes/students', {
      class_id: classId,
    }),

  removeStudent: (classId: number, studentId: number) =>
    post<{ removed_student_id: number }>('/classes/remove-student', {
      class_id: classId,
      student_id: studentId,
    }),

  /** 重新生成班级邀请码（迭代 v2.1）：旧码立即失效，已入班学生不受影响 */
  regenerateInvite: (classId: number) =>
    post<{ class: ClassInfo; invite_code: string }>('/classes/regenerate-invite', {
      class_id: classId,
    }),

  /** 重新生成学生绑定码（迭代 v2.1）：旧码立即失效，已有家长关系不受影响 */
  regenerateBindCode: (studentId: number) =>
    post<{ student_id: number; bind_code: string }>('/classes/regenerate-bind-code', {
      student_id: studentId,
    }),
}

export interface CreateHomeworkParams {
  class_id: number
  title: string
  description?: string
  subject?: string
  deadline: string
}

export const homeworkApi = {
  create: (params: CreateHomeworkParams) =>
    post<{ homework: Homework }>('/homework/create', params as unknown as Record<string, unknown>),

  list: (classId: number, page = 1, size = 20) =>
    post<PageResult<Homework>>('/homework/list', {
      class_id: classId,
      page,
      size,
    }),

  today: () =>
    post<{ list: Homework[]; total: number; class_id: number | null }>('/homework/today'),

  detail: (homeworkId: number) =>
    post<{ homework: Homework }>('/homework/detail', { homework_id: homeworkId }),

  records: (homeworkId: number) =>
    post<{
      homework: Homework
      records: HomeworkRecordRow[]
      total_students: number
      submitted_count: number
    }>('/homework/records', { homework_id: homeworkId }),

  remove: (homeworkId: number) =>
    post<{ deleted_id: number }>('/homework/delete', { homework_id: homeworkId }),

  /** 老师批改作业：打分 + 评语，积分按差额补发/回扣。 */
  review: (homeworkId: number, studentId: number, score: number, comment?: string) =>
    post<{
      record: HomeworkRecord
      points_delta: number
      awarded_points: number
    }>('/homework/review', {
      homework_id: homeworkId,
      student_id: studentId,
      score,
      comment: comment ?? null,
    }),

  /** 待批改列表：已提交但未批改的作业。 */
  pending: (page = 1, size = 20) =>
    post<{
      list: PendingReviewRow[]
      total: number
      page: number
      size: number
    }>('/homework/pending', { page, size }),

  start: (homeworkId: number) =>
    post<{ record: HomeworkRecord; already_started: boolean }>('/homework/start', {
      homework_id: homeworkId,
    }),

  /** 提交作业为 multipart（PRD 5.3）。 */
  submit: async (
    homeworkId: number,
    payload: { textContent?: string; file?: File | null },
  ) => {
    const form = new FormData()
    form.append('homework_id', String(homeworkId))
    if (payload.textContent) form.append('text_content', payload.textContent)
    if (payload.file) form.append('file', payload.file)

    const res = await client.post('/homework/submit', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const body = res.data
    if (body.code !== 0) {
      const err = new Error(body.message) as Error & { code?: number }
      err.code = body.code
      throw err
    }
    return body.data as { record: HomeworkRecord }
  },
}