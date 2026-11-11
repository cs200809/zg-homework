/**
 * 服务端 HTTP 客户端。
 *
 * 独立性约束（PRD 2.2.1）：
 * - 仅通过 HTTP 与 zg-tsp-server 通信，不引用服务端任何源码
 * - 基地址取自构建期配置 VITE_API_BASE_URL，代码中不硬编码
 * - 服务端不可用时统一抛出网络错误，由调用方降级处理，不使应用崩溃
 */
import axios, { AxiosError } from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/homework_api'

/** 统一响应结构（PRD 3.1） */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 业务错误码（PRD 3.1） */
export const CODE = {
  OK: 0,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  RATE_LIMIT: 429,
  SERVER_ERROR: 500,
} as const

/** 服务端不可达 —— 前端据此降级展示，而非当作业务错误 */
export class ServiceUnavailableError extends Error {
  constructor(message = '服务端不可用') {
    super(message)
    this.name = 'ServiceUnavailableError'
  }
}

export const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // 无响应：网络不通 / 服务端未启动 / 跨域被拒
    if (!error.response) {
      return Promise.reject(new ServiceUnavailableError())
    }
    return Promise.reject(error)
  },
)

/** 从文件下载的 HTTP 错误中读取服务端 JSON 文案，解析失败时使用默认文案。 */
export async function downloadErrorMessage(error: unknown, fallback: string): Promise<string> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    const blob = error.response.data
    if (blob.type.toLowerCase().includes('json')) {
      try {
        const payload: unknown = JSON.parse(await blob.text())
        if (payload && typeof payload === 'object' && 'message' in payload &&
            typeof payload.message === 'string' && payload.message.trim()) {
          return payload.message
        }
      } catch {
        // 非法 JSON 或读取失败时保留默认文案。
      }
    }
    return fallback
  }
  return error instanceof Error ? error.message : fallback
}

/**
 * 统一 POST 调用（全 POST + Body 约定，PRD 3.1）。
 * 返回 data 字段；业务错误以 { code, message } 抛出。
 */
export async function post<T = unknown>(
  path: string,
  body: Record<string, unknown> = {},
): Promise<T> {
  const res = await client.post<ApiResponse<T>>(path, body)
  const payload = res.data
  if (payload.code !== CODE.OK) {
    const err = new Error(payload.message) as Error & { code?: number }
    err.code = payload.code
    throw err
  }
  return payload.data
}

/**
 * 把服务端返回的相对文件路径拼成可访问的绝对地址（迭代 v2.1）。
 *
 * 相对路径拼接在 API 基地址后，例如 /uploads/... 对应
 * /homework_api/uploads/...；绝对 URL 保持不变。
 */
export function fileUrl(relativePath: string): string {
  if (!relativePath) return ''
  if (/^https?:\/\//i.test(relativePath)) return relativePath
  const base = API_BASE_URL.replace(/\/$/, '')
  return `${base}${relativePath.startsWith('/') ? '' : '/'}${relativePath}`
}