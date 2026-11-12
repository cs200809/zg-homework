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
  Upload,
} from 'antd'

import { fileUrl } from '../../api/client'
import { articleApi } from '../../api/student'
import type { Article, ArticleStats } from '../../api/types'

/** 文章标题展示：标题本身可能已带书名号，避免出现「《《咏鹅》》」。 */
function displayTitle(title: string): string {
  const t = title.trim()
  return /^《.*》$/.test(t) ? t : `《${t}》`
}

export default function TeacherArticles() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [fileList, setFileList] = useState<File[]>([])

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

  async function onExportPdf(article: Article) {
    try {
      const r = await articleApi.exportPdf(article.id)
      window.open(fileUrl(r.file_url), '_blank')
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导出失败')
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
        title: `${displayTitle(article.title)} 阅读统计`,
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
                {
                  title: '学生姓名',
                  dataIndex: 'student_name',
                  render: (v: string | null, r) => v || `学生${r.student_id}`,
                },
                { title: '学生ID', dataIndex: 'student_id', width: 90 },
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
            width: 280,
            render: (_: unknown, r) => (
              <>
                <Button size="small" onClick={() => showRecords(r)}>
                  阅读记录
                </Button>
                <Button size="small" style={{ marginLeft: 8 }} onClick={() => onExportPdf(r)}>
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

      <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
        提示：老师仅能管理自己发布的文章；admin 可管理全部文章。
      </Typography.Paragraph>
    </Card>
  )
}