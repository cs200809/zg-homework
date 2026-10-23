/** 认证接口（PRD 5.1）。 */

import { post } from './client'
import type { LoginResult, UserInfo } from './types'

export interface RegisterParams {
  username: string
  password: string
  role: 'student' | 'parent' | 'teacher'
  nickname?: string
  teacher_invite_code?: string
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