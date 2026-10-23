/** admin 邀请码管理（PRD 5.8.1、9 admin 端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Table,
  Tag,
  Typography,
} from 'antd'
import { CopyOutlined } from '@ant-design/icons'

import { inviteApi } from '../../api/parent'
import type { InviteCode } from '../../api/types'

const STATUS_TAG: Record<InviteCode['status'], { color: string; text: string }> = {
  unused: { color: 'success', text: '未使用' },
  used: { color: 'default', text: '已使用' },
  expired: { color: 'warning', text: '已过期' },
  revoked: { color: 'red', text: '已撤销' },
}

export default function AdminInvites() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<InviteCode[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string | undefined>()
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await inviteApi.list(page, 20, status)
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, status, message])

  useEffect(() => {
    void load()
  }, [load])

  async function onCreate(values: { count: number; expire_days: number }) {
    try {
      const r = await inviteApi.create(values.count, values.expire_days)
      Modal.success({
        title: `已生成 ${r.count} 个邀请码`,
        content: (
          <div>
            <p>请复制并分发给老师：</p>
            <Typography.Paragraph
              copyable={{ text: r.codes.join('\n'), tooltips: ['复制全部', '已复制'] }}
              style={{ background: '#fafafa', padding: 8, wordBreak: 'break-all' }}
            >
              {r.codes.join('  ')}
            </Typography.Paragraph>
            <p>有效期至：{new Date(r.expire_at).toLocaleString()}</p>
          </div>
        ),
      })
      form.resetFields()
      setPage(1)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '生成失败')
    }
  }

  async function onRevoke(r: InviteCode) {
    try {
      await inviteApi.revoke(r.id)
      message.success('已撤销')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '撤销失败')
    }
  }

  return (
    <Card
      title="老师邀请码管理"
      extra={
        <Select
          allowClear
          placeholder="全部状态"
          style={{ width: 140 }}
          value={status}
          onChange={(v) => {
            setPage(1)
            setStatus(v)
          }}
          options={Object.entries(STATUS_TAG).map(([k, v]) => ({ value: k, label: v.text }))}
        />
      }
    >
      <Card size="small" style={{ marginBottom: 16 }}>
        <Form
          form={form}
          layout="inline"
          onFinish={onCreate}
          initialValues={{ count: 5, expire_days: 7 }}
        >
          <Form.Item name="count" label="生成数量" rules={[{ required: true }]}>
            <InputNumber min={1} max={50} />
          </Form.Item>
          <Form.Item name="expire_days" label="有效期(天)" rules={[{ required: true }]}>
            <InputNumber min={1} max={365} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              批量生成
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Table<InviteCode>
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
        locale={{ emptyText: '暂无邀请码' }}
        columns={[
          {
            title: '邀请码',
            dataIndex: 'code',
            render: (v: string) => (
              <Typography.Text copyable={{ text: v, tooltips: ['复制', '已复制'] }}>{v}</Typography.Text>
            ),
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 100,
            render: (v: InviteCode['status']) => {
              const t = STATUS_TAG[v] ?? { color: 'default', text: v }
              return <Tag color={t.color}>{t.text}</Tag>
            },
          },
          {
            title: '过期时间',
            dataIndex: 'expire_at',
            width: 170,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : '不过期'),
          },
          {
            title: '使用时间',
            dataIndex: 'used_at',
            width: 170,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
          },
          {
            title: '操作',
            width: 100,
            render: (_: unknown, r) =>
              r.status === 'unused' ? (
                <Popconfirm
                  title="确认撤销该邀请码？"
                  onConfirm={() => onRevoke(r)}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button size="small" danger>
                    撤销
                  </Button>
                </Popconfirm>
              ) : (
                <Typography.Text type="secondary">-</Typography.Text>
              ),
          },
        ]}
      />

      <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
        <CopyOutlined /> 邀请码一码一用，被老师注册使用后自动失效。
      </Typography.Paragraph>
    </Card>
  )
}