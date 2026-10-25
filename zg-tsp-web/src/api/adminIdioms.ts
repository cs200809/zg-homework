/** admin 成语题库管理接口（PRD 5.8.6）。 */

import { post } from './client'
import type { PageResult } from './classes'

export interface IdiomQuestion {
  id: number
  prompt: string
  answer: string
  distractors: string[]
  difficulty: string
  enabled: boolean
  created_at: string | null
}

export interface IdiomImportItem {
  prompt: string
  answer: string
  distractors?: string[]
  difficulty?: string
}

export const idiomAdminApi = {
  /** 批量导入（单次上限 1000 条） */
  import: (items: IdiomImportItem[], mode: 'skip' | 'overwrite' = 'skip') =>
    post<{
      success_count: number
      updated_count: number
      skipped_count: number
      duplicates_in_batch: number
    }>('/admin/idioms/import', { items, mode }),

  /** 列表（关键词 / 启用状态筛选 + 分页） */
  list: (params: { page?: number; size?: number; keyword?: string; enabled?: boolean } = {}) =>
    post<PageResult<IdiomQuestion>>('/admin/idioms/list', params as Record<string, unknown>),

  update: (params: {
    question_id: number
    prompt?: string
    answer?: string
    distractors?: string[]
    difficulty?: string
    enabled?: boolean
  }) =>
    post<{ question: IdiomQuestion }>('/admin/idioms/update', params as Record<string, unknown>),

  remove: (questionId: number) =>
    post<{ deleted_id: number }>('/admin/idioms/delete', { question_id: questionId }),

  batchRemove: (questionIds: number[]) =>
    post<{ deleted_count: number }>('/admin/idioms/batch-delete', { question_ids: questionIds }),
}
