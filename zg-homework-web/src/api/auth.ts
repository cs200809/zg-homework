/** 认证接口（PRD 5.1）。 */

import { post } from './client'
import type { LoginResult, UserInfo } from './types'

export interface RegisterParams {
  username: string
  password: string
  role: 'student' | 'parent' | 'teacher'
  nickname?: string
  /** 老师注册码（一码一用） */
  teacher_invite_code?: string
  /** 学生注册码：班级邀请码（多学生可用） */
  class_invite_code?: string
  /** 家长注册码：学生绑定码（多家长可用） */
  bind_code?: string
}

export const authApi = {
  register: (params: RegisterParams) =>
    post<{ user: UserInfo }>('/auth/register', params as unknown as Record<string, unknown>),

  login: (username: string, password: string) =>
    post<LoginResult>('/auth/login', { username, password }),

  me: () => post<{ user: UserInfo }>('/auth/me'),

  changePassword: (oldPassword: string, newPassword: string) =>
    post<{ message: string }>('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    }),
}