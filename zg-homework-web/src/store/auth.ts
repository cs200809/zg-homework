/** 登录状态（Zustand）。token 存 localStorage（PRD 5.1）。 */

import { create } from 'zustand'
import { authApi } from '../api/auth'
import type { Role, UserInfo } from '../api/types'

const TOKEN_KEY = 'token'
const USER_KEY = 'user'

interface AuthState {
  token: string | null
  user: UserInfo | null
  /** 初始化时是否已尝试从本地恢复登录态 */
  initialized: boolean
  loading: boolean

  init: () => Promise<void>
  login: (username: string, password: string) => Promise<UserInfo>
  logout: () => void
  setUser: (user: UserInfo) => void
  mustChangePassword: () => boolean
}

function readStoredUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserInfo
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: readStoredUser(),
  initialized: false,
  loading: false,

  /** 启动时用本地 token 拉一次 /auth/me，确认 token 仍有效。 */
  init: async () => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      set({ initialized: true })
      return
    }
    try {
      const { user } = await authApi.me()
      localStorage.setItem(USER_KEY, JSON.stringify(user))
      set({ user, token, initialized: true })
    } catch {
      // token 失效（过期或被禁用）→ 清理本地状态
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      set({ user: null, token: null, initialized: true })
    }
  },

  login: async (username, password) => {
    set({ loading: true })
    try {
      const result = await authApi.login(username, password)
      localStorage.setItem(TOKEN_KEY, result.token)
      localStorage.setItem(USER_KEY, JSON.stringify(result.user))
      set({ token: result.token, user: result.user, initialized: true })
      return result.user
    } finally {
      set({ loading: false })
    }
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: null, user: null })
  },

  setUser: (user) => {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    set({ user })
  },

  mustChangePassword: () => get().user?.must_change_password === true,
}))

/** 各角色的首页路径（PRD 9）。 */
export const ROLE_HOME: Record<Role, string> = {
  student: '/student',
  parent: '/parent',
  teacher: '/teacher',
  admin: '/admin',
}

/** 角色中文名。 */
export const ROLE_LABEL: Record<Role, string> = {
  admin: '管理员',
  teacher: '老师',
  student: '学生',
  parent: '家长',
}