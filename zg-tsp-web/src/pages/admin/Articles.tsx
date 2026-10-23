/** admin 文章管理（PRD 5.8.4、9 admin 端）。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Input, Popconfirm, Select, Table, Tag } from 'antd'

import { articleApi } from '../../api/student'
import type { Article } from '../../api/types'

export default function AdminArticles() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // admin 端不加 status 过滤即可看到全部；这里按需在服务端过滤
      const r = await articleApi.list(page, 20)
      // 服务端 list 目前按角色返回，这里在前端做一次筛选（数据量小，可接受）
      let list = r.list
      if (status) list = list.filter((a) => a.status === status)
      if (keyword.trim()) {
        const k = keyword.trim()
        list = list.filter((a) => a.title.includes(k))
      }
      setRows(list)
      setTotal(list.length)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, status, keyword, message])

  useEffect(() => {
    void load()
  }, [load])

  async function onDelete(a: Article) {
    try {
      await articleApi.remove(a.id)
      message.success('已删除')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <Card
      title="文章管理（全量）"
      extra={
        <span style={{ display: 'inline-flex', gap: 8 }}>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 130 }}
            value={status}
            onChange={(v) => {
              setPage(1)
              setStatus(v)
            }}
            options={[
              { value: 'published', label: '已发布' },
              { value: 'hidden', label: '已隐藏' },
            ]}
          />
          <Input.Search
            allowClear
            placeholder="搜索标题"
            style={{ width: 200 }}
            onSearch={(v) => {
              setPage(1)
              setKeyword(v)
            }}
          />
        </span>
      }
    >
      <Table<Article>
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
          { title: '标题', dataIndex: 'title' },
          {
            title: '作者角色',
            dataIndex: 'created_role',
            width: 100,
            render: (v: string) => (
              <Tag color={v === 'admin' ? 'purple' : 'blue'}>
                {v === 'admin' ? '管理员' : '老师'}
              </Tag>
            ),
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 100,
            render: (v: string) => (
              <Tag color={v === 'published' ? 'success' : 'default'}>
                {v === 'published' ? '已发布' : '已隐藏'}
              </Tag>
            ),
          },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 170,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
          },
          {
            title: '操作',
            width: 100,
            render: (_: unknown, r) => (
              <Popconfirm
                title="确认删除该文章？"
                onConfirm={() => onDelete(r)}
                okText="确认"
                cancelText="取消"
              >
                <Button size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />
    </Card>
  )
}
