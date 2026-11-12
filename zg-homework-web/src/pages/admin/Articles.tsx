/** admin 文章管理（PRD 5.8.4、9 admin 端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Table,
  Tag,
  Upload,
} from 'antd'

import { fileUrl } from '../../api/client'
import { articleApi } from '../../api/student'
import type { Article } from '../../api/types'

export default function AdminArticles() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [fileList, setFileList] = useState<File[]>([])

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

  async function onCreate(values: { title: string; content?: string }) {
    try {
      await articleApi.createFile(values.title, values.content ?? '', fileList[0] ?? null)
      message.success('文章发布成功')
      form.resetFields()
      setFileList([])
      setCreating(false)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '发布失败')
    }
  }

  async function onExportPdf(a: Article) {
    try {
      const r = await articleApi.exportPdf(a.id)
      window.open(fileUrl(r.file_url), '_blank')
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导出失败')
    }
  }

  return (
    <Card
      title="文章管理（全量）"
      extra={
        <span style={{ display: 'inline-flex', gap: 8 }}>
          <Button type="primary" onClick={() => setCreating(true)}>
            发布文章
          </Button>
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
            width: 180,
            render: (_: unknown, r) => (
              <>
                <Button size="small" onClick={() => onExportPdf(r)}>
                  导出 PDF
                </Button>
                <Popconfirm
                  title="确认删除该文章？"
                  onConfirm={() => onDelete(r)}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button size="small" danger style={{ marginLeft: 8 }}>
                    删除
                  </Button>
                </Popconfirm>
              </>
            ),
          },
        ]}
      />

      <Modal
        title="发布文章"
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={() => form.submit()}
        okText="发布"
        cancelText="取消"
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={onCreate}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="文章标题" />
          </Form.Item>
          <Form.Item
            name="content"
            label="正文"
            extra="纯文本可直接填写；上传 PDF / Word 时服务端会自动抽取正文，二选一即可"
          >
            <Input.TextArea rows={10} placeholder="文章正文内容" />
          </Form.Item>
          <Form.Item label="文章文件（可选，支持 PDF / Word）">
            <Upload
              accept=".pdf,.docx"
              maxCount={1}
              beforeUpload={(f) => {
                setFileList([f])
                return false
              }}
              onRemove={() => setFileList([])}
              fileList={fileList.map((f) => ({
                uid: f.name,
                name: f.name,
                status: 'done' as const,
              }))}
            >
              <Button>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
