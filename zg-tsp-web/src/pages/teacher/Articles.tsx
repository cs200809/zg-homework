/** 老师端文章管理：发布 + 阅读记录（PRD 5.5、9 老师端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Table,
  Tag,
  Typography,
} from 'antd'

import { articleApi } from '../../api/student'
import type { Article, ArticleStats } from '../../api/types'

export default function TeacherArticles() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // 老师端不加 status 过滤，可看到自己发布的全部文章
      const r = await articleApi.list(1, 50)
      setRows(r.list)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  async function onCreate(values: { title: string; content: string }) {
    try {
      await articleApi.create(values.title, values.content)
      message.success('文章发布成功')
      form.resetFields()
      setCreating(false)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '发布失败')
    }
  }

  async function onDelete(article: Article) {
    try {
      await articleApi.remove(article.id)
      message.success('已删除')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  async function showRecords(article: Article) {
    try {
      const r = await articleApi.records(article.id)
      const s: ArticleStats = r.stats
      Modal.info({
        title: `《${article.title}》阅读统计`,
        content: (
          <div>
            <p>阅读人数：{s.reader_count}</p>
            <p>读完人数：{s.finished_count}</p>
            <p>总时长：{Math.floor(s.total_duration_seconds / 60)} 分 {s.total_duration_seconds % 60} 秒</p>
            <Table
              size="small"
              rowKey="student_id"
              pagination={false}
              dataSource={r.records}
              locale={{ emptyText: '暂无阅读记录' }}
              columns={[
                { title: '学生ID', dataIndex: 'student_id' },
                {
                  title: '时长(分)',
                  dataIndex: 'duration_seconds',
                  render: (v: number) => Math.floor(v / 60),
                },
                {
                  title: '读完',
                  dataIndex: 'finished',
                  render: (v: boolean) => (v ? <Tag color="success">已读完</Tag> : '未读完'),
                },
                { title: '积分', dataIndex: 'points' },
              ]}
            />
          </div>
        ),
        width: 720,
      })
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载阅读记录失败')
    }
  }

  return (
    <Card
      title="文章管理"
      extra={
        <Button type="primary" onClick={() => setCreating(true)}>
          发布文章
        </Button>
      }
    >
      <Table<Article>
        rowKey="id"
        dataSource={rows}
        loading={loading}
        locale={{ emptyText: '还没有发布文章' }}
        columns={[
          { title: '标题', dataIndex: 'title' },
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
            width: 160,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
          },
          {
            title: '操作',
            width: 200,
            render: (_: unknown, r) => (
              <>
                <Button size="small" onClick={() => showRecords(r)}>
                  阅读记录
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
          <Form.Item name="content" label="正文" rules={[{ required: true, message: '请输入正文' }]}>
            <Input.TextArea rows={10} placeholder="文章正文内容" />
          </Form.Item>
        </Form>
      </Modal>

      <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
        提示：老师仅能管理自己发布的文章；admin 可管理全部文章。
      </Typography.Paragraph>
    </Card>
  )
}