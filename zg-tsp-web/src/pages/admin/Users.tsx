/** admin 用户管理（PRD 5.8.2、9 admin 端）。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Form, Input, Modal, Popconfirm, Select, Table, Tag } from 'antd'

import { userApi } from '../../api/parent'
import type { AdminUser, Role } from '../../api/types'

const ROLE_LABEL: Record<Role, string> = {
  admin: '管理员',
  teacher: '老师',
  student: '学生',
  parent: '家长',
}

export default function AdminUsers() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<{ role?: Role; status?: string; keyword?: string }>({})
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await userApi.list({ page, size: 20, ...filters })
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, filters, message])

  useEffect(() => {
    void load()
  }, [load])

  async function toggle(u: AdminUser) {
    try {
      if (u.status === 'active') {
        await userApi.disable(u.id)
        message.success(`已禁用 ${u.username}`)
      } else {
        await userApi.enable(u.id)
        message.success(`已启用 ${u.username}`)
      }
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  async function resetPassword(u: AdminUser) {
    try {
      const r = await userApi.resetPassword(u.id)
      Modal.info({
        title: `重置 ${u.username} 的密码`,
        content: (
          <div>
            <p>临时密码：</p>
            <Input
              defaultValue={r.temp_password}
              readOnly
              style={{ fontFamily: 'monospace' }}
              onFocus={(e) => e.target.select()}
            />
            <p style={{ marginTop: 8, color: '#999' }}>
              用户下次登录将被强制改密（PRD 5.8.2）。
            </p>
          </div>
        ),
      })
    } catch (e) {
      message.error(e instanceof Error ? e.message : '重置失败')
    }
  }

  return (
    <Card
      title="用户管理"
      extra={
        <Button
          onClick={() => {
            setFilters({})
            form.resetFields()
            setPage(1)
          }}
        >
          清空筛选
        </Button>
      }
    >
      <Form
        form={form}
        layout="inline"
        style={{ marginBottom: 16 }}
        onFinish={(v) => {
          setPage(1)
          setFilters(v as typeof filters)
        }}
      >
        <Form.Item name="role" label="角色">
          <Select
            allowClear
            placeholder="全部角色"
            style={{ width: 120 }}
            options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ value: k, label: v }))}
          />
        </Form.Item>
        <Form.Item name="status" label="状态">
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 120 }}
            options={[
              { value: 'active', label: '启用' },
              { value: 'disabled', label: '禁用' },
            ]}
          />
        </Form.Item>
        <Form.Item name="keyword" label="关键词">
          <Input placeholder="用户名/昵称" allowClear />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit">
            查询
          </Button>
        </Form.Item>
      </Form>

      <Table<AdminUser>
        rowKey="id"
        dataSource={rows}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: setPage,
          showSizeChanger: false,
        }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '用户名', dataIndex: 'username' },
          { title: '昵称', dataIndex: 'nickname', render: (v: string | null) => v || '-' },
          {
            title: '角色',
            dataIndex: 'role',
            width: 90,
            render: (v: Role) => <Tag>{ROLE_LABEL[v]}</Tag>,
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 90,
            render: (v: string) => (
              <Tag color={v === 'active' ? 'success' : 'red'}>
                {v === 'active' ? '启用' : '禁用'}
              </Tag>
            ),
          },
          {
            title: '积分',
            dataIndex: 'total_points',
            width: 80,
            render: (v: number, r) => (r.role === 'student' ? v : '-'),
          },
          {
            title: '操作',
            width: 240,
            render: (_: unknown, r) => {
              if (r.role === 'admin') return <span style={{ color: '#999' }}>不可操作</span>
              return (
                <>
                  <Popconfirm
                    title={`确认${r.status === 'active' ? '禁用' : '启用'} ${r.username}？`}
                    onConfirm={() => toggle(r)}
                    okText="确认"
                    cancelText="取消"
                  >
                    <Button size="small" danger={r.status === 'active'}>
                      {r.status === 'active' ? '禁用' : '启用'}
                    </Button>
                  </Popconfirm>
                  <Button
                    size="small"
                    style={{ marginLeft: 8 }}
                    onClick={() => resetPassword(r)}
                  >
                    重置密码
                  </Button>
                </>
              )
            },
          },
        ]}
      />
    </Card>
  )
}
