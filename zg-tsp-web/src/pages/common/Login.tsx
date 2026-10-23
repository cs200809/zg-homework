/** 登录页（PRD 9 公共）。 */

import { useState } from 'react'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'

import { ROLE_HOME, useAuthStore } from '../../store/auth'
import { ServiceUnavailableError } from '../../api/client'

export default function LoginPage() {
  const [form] = Form.useForm()
  const login = useAuthStore((s) => s.login)
  const loading = useAuthStore((s) => s.loading)
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  async function onFinish(values: { username: string; password: string }) {
    setError(null)
    try {
      const user = await login(values.username, values.password)
      // admin 首登必须改密（PRD 5.1）
      if (user.must_change_password) {
        navigate('/change-password', { replace: true })
      } else {
        navigate(ROLE_HOME[user.role], { replace: true })
      }
    } catch (e) {
      if (e instanceof ServiceUnavailableError) {
        setError('无法连接服务端，请检查网络或稍后重试')
      } else {
        setError(e instanceof Error ? e.message : '登录失败')
      }
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
      <Card style={{ width: 380 }} title="zg-tsp 平台登录">
        {error && (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />
        )}

        <Form form={form} onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>
              登录
            </Button>
          </Form.Item>
        </Form>

        <Typography.Paragraph style={{ textAlign: 'center', marginBottom: 0 }}>
          还没有账号？<Link to="/register">立即注册</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  )
}

