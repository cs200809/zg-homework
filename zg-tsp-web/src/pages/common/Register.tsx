/** 注册页（PRD 5.1、9 公共）：选角色，选「老师」显示邀请码输入。 */

import { useState } from 'react'
import { Alert, Button, Card, Form, Input, Radio, Typography, App } from 'antd'
import { Link, useNavigate } from 'react-router-dom'

import { authApi } from '../../api/auth'
import { ServiceUnavailableError } from '../../api/client'

type Role = 'student' | 'parent' | 'teacher'

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
                setRole(e.target.value)
                form.setFieldsValue({ teacher_invite_code: undefined })
              }}
              options={[
                { label: '学生', value: 'student' },
                { label: '家长', value: 'parent' },
                { label: '老师', value: 'teacher' },
              ]}
            />
          </Form.Item>

          <Form.Item
            label="用户名"
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, max: 20, message: '用户名 3~20 位' },
            ]}
          >
            <Input placeholder="3~20 位，登录时使用" />
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

          {/* 老师必须携带邀请码（PRD 5.1） */}
          {role === 'teacher' && (
            <Form.Item
              label="老师邀请码"
              name="teacher_invite_code"
              rules={[{ required: true, message: '老师注册必须填写邀请码' }]}
            >
              <Input placeholder="向管理员申请获得" />
            </Form.Item>
          )}

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