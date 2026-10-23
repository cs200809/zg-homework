/** 学生端接口：签到、阅读、游戏、积分（PRD 5.4、5.5、5.6）。 */

import { post } from './client'
import type { PageResult } from './classes'
import type {
  Article,
  ArticleStats,
  GameRecord,
  IdiomQuestionView,
  PointLog,
  PointType,
  RankItem,
  SudokuBoard,
} from './types'

// ---------- 签到（PRD 5.4） ----------
export const checkinApi = {
  do: () =>
    post<{
      already_checked: boolean
      checkin_date: string
      points: number
      streak: number
      streak_bonus?: number
      total_points: number
    }>('/checkin/do'),

  status: () =>
    post<{
      checked_in: boolean
      checkin_date: string
      points: number
      streak: number
      total_points: number
      recent: { date: string; points: number; streak: number }[]
    }>('/checkin/status'),
}

// ---------- 积分（PRD 5.4） ----------
export const pointsApi = {
  rank: (type: 'day' | 'total', page = 1, size = 50) =>
    post<{
      type: string
      list: RankItem[]
      total: number
      page: number
      size: number
      my_rank: number
    }>('/points/rank', { type, page, size }),

  log: (page = 1, size = 20, type?: PointType) =>
    post<PageResult<PointLog>>('/points/log', {
      page,
      size,
      ...(type ? { type } : {}),
    }),

  summary: () =>
    post<{
      total_points: number
      gained_today: number
      total_gained: number
      total_consumed: number
      gained_today_rank: number
    }>('/points/summary'),
}

// ---------- 阅读（PRD 5.5） ----------
export const articleApi = {
  list: (page = 1, size = 20) =>
    post<PageResult<Article>>('/articles/list', { page, size }),

  detail: (articleId: number) =>
    post<{ article: Article }>('/articles/detail', { article_id: articleId }),

  /** 心跳上报。服务端校验 30s±10s，异常不计分（PRD 5.5）。 */
  heartbeat: (articleId: number, seconds: number) =>
    post<{
      accepted: boolean
      reason?: string
      duration_seconds: number
      points: number
      points_gained?: number
      finished: boolean
    }>('/articles/heartbeat', { article_id: articleId, seconds }),

  finish: (articleId: number) =>
    post<{
      already_finished: boolean
      points_gained: number
      points: number
      duration_seconds: number
    }>('/articles/finish', { article_id: articleId }),

  records: (articleId: number) =>
    post<{
      article: Article
      records: {
        student_id: number
        duration_seconds: number
        finished: boolean
        points: number
        read_date: string | null
      }[]
      stats: ArticleStats
    }>('/articles/records', { article_id: articleId }),

  remove: (articleId: number) =>
    post<{ deleted_id: number }>('/articles/delete', { article_id: articleId }),

  /** 发布文章（teacher / admin，PRD 5.5）。 */
  create: (title: string, content: string, cover?: string) =>
    post<{ article: Article }>('/articles/create', {
      title,
      content,
      ...(cover ? { cover } : {}),
    }),
}

// ---------- 游戏（PRD 5.6） ----------
export const gamesApi = {
  sudokuStart: (difficulty: 'easy' | 'medium' | 'hard') =>
    post<SudokuBoard>('/games/sudoku/start', { difficulty }),

  sudokuResult: (puzzleId: string, duration: number, success: boolean, board?: number[][]) =>
    post<{ success: boolean; points: number; duration_seconds: number }>(
      '/games/sudoku/result',
      {
        puzzle_id: puzzleId,
        duration,
        success,
        ...(board ? { board } : {}),
      },
    ),

  idiomStart: () =>
    post<{ session_id: string; duration_seconds: number; total_questions: number }>(
      '/games/idiom/start',
    ),

  idiomQuestion: (sessionId: string) =>
    post<{
      session_id: string
      question: IdiomQuestionView
      elapsed_seconds: number
      remaining_seconds: number
    }>('/games/idiom/question', { session_id: sessionId }),

  idiomAnswer: (sessionId: string, answer: string) =>
    post<{
      correct: boolean
      right_answer: string
      correct_count: number
      wrong_count: number
      remaining_seconds: number
    }>('/games/idiom/answer', { session_id: sessionId, answer }),

  idiomResult: (sessionId: string) =>
    post<{
      correct_count: number
      wrong_count: number
      duration_seconds: number
      points: number
    }>('/games/idiom/result', { session_id: sessionId }),

  records: (page = 1, size = 20) =>
    post<PageResult<GameRecord>>('/games/records', { page, size }),
}