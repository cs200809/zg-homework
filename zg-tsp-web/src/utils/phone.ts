/**
 * 手机号格式校验（迭代 v2.1）。
 *
 * **用户名即手机号**：注册时用户名必须是手机号，且需校验唯一性（PRD 5.1）。
 * 校验规则为 `^1[3-9]\d{9}$`，与
 * `zg-tsp-server/app/schemas/auth.py` 的 `PHONE_PATTERN` 保持一致。
 *
 * 规则散落在多个页面会导致「注册能过、登录不能过」这类不一致，
 * 故集中到本模块，由 Register / Login 页共用。
 */

/** 手机号格式：1 开头，第二位 3-9，共 11 位 */
export const PHONE_RE = /^1[3-9]\d{9}$/

/** 纯数字（用于区分「像手机号的输入」与「账号名」） */
const DIGITS_ONLY_RE = /^\d+$/

/**
 * 登录用户名校验。
 *
 * 返回错误文案，通过则返回 null。
 *
 * **只在输入为纯数字时校验手机号格式**，原因：
 *   - 普通用户的用户名就是手机号。输入 10 位、12 位等纯数字，
 *     基本可断定是手机号输错了，此时给出「请输入正确的 11 位手机号」
 *     比服务端含糊的「用户名或密码错误」有用得多。
 *   - 但 admin 的用户名是 `admin`（非手机号），且 Web 端 admin 与普通用户
 *     共用同一个登录页。若一律强制校验手机号，会把管理员挡在门外。
 *
 * 因此非数字输入不在前端拦截，交由服务端按账号查询判定。
 */
export function checkLoginUsername(username: string | undefined | null): string | null {
  const value = (username ?? '').trim()
  if (!value) return '请输入用户名'
  if (DIGITS_ONLY_RE.test(value) && !PHONE_RE.test(value)) {
    return '请输入正确的 11 位手机号'
  }
  return null
}
