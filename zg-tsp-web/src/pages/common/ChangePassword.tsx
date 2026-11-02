/** 修改密码页：admin 首登强制跳转至此（PRD 5.1）。 */

import { useState } from 'react'
import { Alert, Button, Card, Form, Input, App } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'

import { authApi } from '../../api/auth'
import { ROLE_HOME, useAuthStore } from '../../store/auth'

export default function ChangePasswordPage() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { user, setUser, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  // 入口通过 router state 传入来源页；无来源（如直接输 URL）时回退到角色首页
  const from = (location.state as { from?: string } | null)?.from
  const { message } = App.useApp()

  const forced = user?.must_change_password === true

  async function onFinish(values: { old_password: string; new_password: string }) {
    setError(null)
    setLoading(true)
    try {
      await authApi.changePassword(values.old_password, values.new_password)
      // 改密成功 → 解除强制标记，回到首页
      if (user) setUser({ ...user, must_change_password: false })
      message.success('密码修改成功')
      navigate(from ?? (user ? ROLE_HOME[user.role] : '/login'), { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : '修改失败')
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
      <Card style={{ width: 380 }} title={forced ? '首次登录，请修改初始密码' : '修改密码'}>
        {error && (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} closable onClose={() => setError(null)} />
        )}
        {forced && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="使用初始密码登录后必须修改密码，修改前无法使用其他功能"
          />
        )}

        <Form form={form} layout="vertical" onFinish={onFinish} size="large">
          <Form.Item label="原密码" name="old_password" rules={[{ required: true, message: '请输入原密码' }]}>
            <Input.Password placeholder="初始密码" />
          </Form.Item>
          <Form.Item
            label="新密码"
            name="new_password"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少 6 位' },
            ]}
          >
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item
            label="确认新密码"
            name="confirm"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator: (_, value) =>
                  !value || getFieldValue('new_password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致')),
              }),
            ]}
          >
            <Input.Password placeholder="再次输入新密码" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading}>
              确认修改
            </Button>
          </Form.Item>
        </Form>

        {!forced && (
          <Button
            type="link"
            block
            onClick={() => {
              logout()
              navigate('/login')
            }}
          >
            退出登录
          </Button>
        )}
      </Card>
    </div>
  )
}