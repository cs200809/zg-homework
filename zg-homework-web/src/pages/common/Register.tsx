/** 注册页（PRD 5.1、9 公共、迭代 v2.1）。
 *
 * 用户名必须是手机号；三类角色各自需要一枚码：
 * - 老师：老师邀请码（一码一用）
 * - 学生：班级邀请码（多学生可用，注册后自动入班）
 * - 家长：学生绑定码（多家长可用，注册后自动绑定）
 */

import { useState } from 'react'
import { Alert, Button, Card, Form, Input, Radio, Typography, App } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { authApi } from '../../api/auth'
import { ServiceUnavailableError } from '../../api/client'
import { PHONE_RE } from '../../utils/phone'

type Role = 'student' | 'parent' | 'teacher'

/** 各角色注册所需的码 */
const CODE_FIELD = {
  teacher: {
    name: 'teacher_invite_code',
    label: '老师邀请码',
    placeholder: '向管理员申请获得',
  },
  student: {
    name: 'class_invite_code',
    label: '班级邀请码',
    placeholder: '向老师索取班级邀请码',
  },
  parent: {
    name: 'bind_code',
    label: '学生绑定码',
    placeholder: '让孩子在「我的」页面查看绑定码',
  },
} as const

export default function RegisterPage() {
  const [form] = Form.useForm()
  const [role, setRole] = useState<Role>('student')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { message } = App.useApp()

  async function onFinish(values: {
    username: string
    password: string
    nickname?: string
    teacher_invite_code?: string
    class_invite_code?: string
    bind_code?: string
  }) {
    setError(null)
    setLoading(true)
    try {
      await authApi.register({
        username: values.username,
        password: values.password,
        role,
        nickname: values.nickname,
        teacher_invite_code: role === 'teacher' ? values.teacher_invite_code : undefined,
        class_invite_code: role === 'student' ? values.class_invite_code : undefined,
        bind_code: role === 'parent' ? values.bind_code : undefined,
      })
      message.success('注册成功，请登录')
      navigate('/login')
    } catch (e) {
      if (e instanceof ServiceUnavailableError) {
        setError('无法连接服务端，请稍后重试')
      } else {
        setError(e instanceof Error ? e.message : '注册失败')
      }
    } finally {
      setLoading(false)
    }
  }

  const code = CODE_FIELD[role]

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 420 }} title="注册新账号">
        {error && (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />
        )}

        <Form form={form} layout="vertical" onFinish={onFinish} size="large">
          <Form.Item label="角色" name="role">
            <Radio.Group
              value={role}
              onChange={(e) => {
                const next = e.target.value as Role
                setRole(next)
                // 切换角色时清空上一角色的码
                form.setFieldsValue({
                  teacher_invite_code: undefined,
                  class_invite_code: undefined,
                  bind_code: undefined,
                })
              }}
              options={[
                { label: '学生', value: 'student' },
                { label: '家长', value: 'parent' },
                { label: '老师', value: 'teacher' },
              ]}
            />
          </Form.Item>

          <Form.Item
            label="用户名（手机号）"
            name="username"
            rules={[
              { required: true, message: '请输入手机号' },
              { pattern: PHONE_RE, message: '请输入正确的 11 位手机号' },
            ]}
          >
            <Input placeholder="11 位手机号，登录时使用" maxLength={11} />
          </Form.Item>

          <Form.Item
            label="密码"
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少 6 位' },
            ]}
          >
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>

          <Form.Item label="昵称（选填）" name="nickname">
            <Input placeholder="留空则与用户名相同" />
          </Form.Item>

          {/* 各角色必须携带对应的码（PRD 5.1、迭代 v2.1） */}
          <Form.Item
            key={role}
            name={code.name}
            label={code.label}
            preserve={false}
            rules={[{ required: true, message: `请输入${code.label}` }]}
          >
            <Input placeholder={code.placeholder} maxLength={12} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>
              注册
            </Button>
          </Form.Item>
        </Form>

        <Typography.Paragraph style={{ textAlign: 'center', marginBottom: 0 }}>
          已有账号？<Link to="/login">返回登录</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
