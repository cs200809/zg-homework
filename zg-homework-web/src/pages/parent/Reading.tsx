import { useEffect, useRef, useState } from 'react'
import { App, Button, Card, Empty, List, Pagination, Select, Space, Spin } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import { parentApi } from '../../api/parent'

import { client, downloadErrorMessage, post } from '../../api/client'
import type { Article, Child } from '../../api/types'

type ArticlePage = { list: Article[]; total: number }

export default function ParentReadingPage() {
  const { id } = useParams()
  const { message } = App.useApp()
  const [children, setChildren] = useState<Child[] | null>(null)
  useEffect(() => {
    let active = true
    parentApi.children().then((result) => { if (active) setChildren(result.list) })
      .catch((error: unknown) => { if (active) { message.error(error instanceof Error ? error.message : '加载孩子失败'); setChildren([]) } })
    return () => { active = false }
  }, [message])
  if (!children) return <Spin />
  return <ParentReading key={id} children={children} initialStudentId={Number(id)} />
}

/** 家长阅读不产生学生阅读计时或积分。 */
function ParentReading({ children, initialStudentId }: { children: Child[]; initialStudentId: number }) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const studentId = initialStudentId
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<Article[]>([])
  const [total, setTotal] = useState(0)
  const [detail, setDetail] = useState<Article | null>(null)
  const [loading, setLoading] = useState(false)
  const [opening, setOpening] = useState(false)
  const [exporting, setExporting] = useState(false)
  const detailRequest = useRef(0)

  useEffect(() => {
    if (!studentId || !children.some((child) => child.student_id === studentId)) return
    let active = true
    setLoading(true)
    setRows([])
    setTotal(0)
    post<ArticlePage>('/parent/articles/list', { student_id: studentId, page, size: 10 })
      .then((result) => {
        if (active) {
          setRows(result.list)
          setTotal(result.total)
        }
      })
      .catch((error: unknown) => {
        if (active) message.error(error instanceof Error ? error.message : '加载文章失败')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [studentId, page, children, message])

  async function openArticle(articleId: number) {
    if (!studentId) return
    const request = ++detailRequest.current
    setOpening(true)
    try {
      const result = await post<{ article: Article }>('/parent/articles/detail', {
        student_id: studentId, article_id: articleId,
      })
      if (request === detailRequest.current) setDetail(result.article)
    } catch (error) {
      if (request === detailRequest.current) message.error(error instanceof Error ? error.message : '加载详情失败')
    } finally {
      if (request === detailRequest.current) setOpening(false)
    }
  }

  async function exportPdf() {
    if (!studentId || !detail || exporting) return
    setExporting(true)
    try {
      const response = await client.post<Blob>('/parent/articles/download', {
        student_id: studentId, article_id: detail.id,
      }, { responseType: 'blob' })
      if (!response.data.type.toLowerCase().includes('application/pdf')) {
        throw new Error('服务端未返回 PDF 文件')
      }
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `${detail.title}.pdf`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (error) {
      message.error(await downloadErrorMessage(error, '导出 PDF 失败'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <Card title="孩子的阅读" style={{ marginTop: 24 }}>
      {children.length === 0 ? <Empty description="请先绑定孩子" /> : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Select
            aria-label="选择孩子"
            value={studentId}
            style={{ minWidth: 180 }}
            options={children.map((child) => ({ value: child.student_id, label: child.nickname || child.username }))}
            onChange={(value) => navigate(`/parent/children/${value}/reading`)}
          />
          {detail ? (
            <Card size="small" title={detail.title} extra={<Button onClick={() => setDetail(null)}>返回列表</Button>}>
              <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{detail.content || '暂无正文'}</div>
              <Button style={{ marginTop: 16 }} loading={exporting} onClick={exportPdf}>下载 PDF</Button>
            </Card>
          ) : (
            <>
              <List
                loading={loading}
                dataSource={rows}
                locale={{ emptyText: '暂无文章' }}
                renderItem={(article) => (
                  <List.Item actions={[
                    <Button key="detail" type="link" disabled={opening} onClick={() => void openArticle(article.id)}>查看详情</Button>,
                  ]}>
                    <List.Item.Meta
                      title={article.title}
                      description={`发布者角色：${article.created_role === 'admin' ? '管理员' : '老师'}`}
                    />
                  </List.Item>
                )}
              />
              <Pagination current={page} pageSize={10} total={total} showSizeChanger={false} onChange={setPage} />
            </>
          )}
        </Space>
      )}
    </Card>
  )
}
