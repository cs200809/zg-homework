import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, App, Button, Card, Descriptions, Empty, Input, List, Pagination, Select, Space, Tag } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import { parentApi } from '../../api/parent'
import { client, downloadErrorMessage, post } from '../../api/client'
import type { ApiResponse } from '../../api/client'
import type { Child, Homework } from '../../api/types'

// Parent homework endpoints are not yet present in the current server snapshot.
// The response shapes follow the existing student homework and article PDF APIs.
type HomeworkPage = { list: Homework[]; total: number }

export default function ParentHomework() {
  const { id, homeworkId } = useParams()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [children, setChildren] = useState<Child[]>([])
  const studentId = Number(id) || undefined
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<Homework[]>([])
  const [total, setTotal] = useState(0)
  const [detail, setDetail] = useState<Homework | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const listRequest = useRef(0)
  const detailRequest = useRef(0)

  useEffect(() => {
    parentApi.children().then((result) => setChildren(result.list)).catch((error) => {
      message.error(error instanceof Error ? error.message : '加载孩子列表失败')
    })
  }, [message])

  useEffect(() => {
    listRequest.current++
    detailRequest.current++
    setRows([])
    setDetail(null)
    setPage(1)
  }, [id])

  const load = useCallback(async () => {
    if (!studentId) return
    const request = ++listRequest.current
    setLoading(true)
    try {
      const result = await post<HomeworkPage>('/parent/homework/list', { student_id: studentId, page, size: 10 })
      if (request !== listRequest.current) return
      setRows(result.list)
      setTotal(result.total)
    } catch (error) {
      if (request !== listRequest.current) return
      setRows([])
      setTotal(0)
      message.error(error instanceof Error ? error.message : '加载作业失败')
    } finally {
      if (request === listRequest.current) setLoading(false)
    }
  }, [studentId, page, message])

  useEffect(() => { void load() }, [load])

  const openHomework = useCallback(async (homeworkId: number) => {
    if (!studentId) return
    const request = ++detailRequest.current
    setBusy(true)
    try {
      const result = await post<{ homework: Homework }>('/parent/homework/detail', { student_id: studentId, homework_id: homeworkId })
      if (request !== detailRequest.current) return
      setDetail(result.homework)
      setText(result.homework.my_record?.text_content || '')
      setFile(null)
    } catch (error) {
      if (request === detailRequest.current) message.error(error instanceof Error ? error.message : '加载详情失败')
    } finally {
      if (request === detailRequest.current) setBusy(false)
    }
  }, [studentId, message])

  useEffect(() => {
    if (homeworkId && studentId) void openHomework(Number(homeworkId))
    else { detailRequest.current++; setDetail(null); setBusy(false) }
    return () => { detailRequest.current++ }
  }, [homeworkId, studentId, openHomework])

  async function submit() {
    if (!studentId || !detail) return
    if (!text.trim() && !file) {
      message.warning('请填写作答内容或选择附件')
      return
    }
    const form = new FormData()
    form.append('student_id', String(studentId))
    form.append('homework_id', String(detail.id))
    form.append('text_content', text)
    if (file) form.append('file', file)
    setBusy(true)
    try {
      const response = await client.post<ApiResponse<unknown>>('/parent/homework/submit', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (response.data.code !== 0) throw new Error(response.data.message)
      message.success('提交成功')
      await openHomework(detail.id)
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提交失败')
    } finally {
      setBusy(false)
    }
  }

  async function exportPdf() {
    if (!studentId || !detail) return
    setBusy(true)
    try {
      const response = await client.post<Blob>('/parent/homework/download', { student_id: studentId, homework_id: detail.id }, { responseType: 'blob' })
      if (!response.data.type.includes('application/pdf')) throw new Error('导出失败：服务端未返回 PDF 文件')
      const url = URL.createObjectURL(response.data)
      try {
        const link = document.createElement('a')
        link.href = url
        link.download = '作业.pdf'
        link.click()
      } finally {
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch (error) {
      message.error(await downloadErrorMessage(error, '导出失败'))
    } finally {
      setBusy(false)
    }
  }

  async function downloadAttachment() {
    if (!studentId || !detail) return
    setBusy(true)
    try {
      const response = await client.post<Blob>('/homework/attachment', { student_id: studentId, homework_id: detail.id }, { responseType: 'blob' })
      if (response.data.type.includes('application/json')) {
        const payload = JSON.parse(await response.data.text()) as { message?: string }
        throw new Error(payload.message || '下载附件失败')
      }
      const url = URL.createObjectURL(response.data)
      try {
        const link = document.createElement('a')
        link.href = url
        const disposition = response.headers['content-disposition'] as string | undefined
        const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
        const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1]
        try { link.download = encoded ? decodeURIComponent(encoded) : filename || '作业附件' }
        catch { link.download = filename || '作业附件' }
        link.click()
      } finally {
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch (error) {
      message.error(await downloadErrorMessage(error, '下载附件失败'))
    } finally {
      setBusy(false)
    }
  }

  const record = detail?.my_record
  const submitted = Boolean(record?.submit_time)
  return (
    <Card title="孩子的作业" style={{ marginTop: 24 }}>
      {children.length === 0 ? <Empty description="请先绑定孩子" /> : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Select
            aria-label="选择孩子"
            value={studentId}
            style={{ minWidth: 180 }}
            options={children.map((child) => ({ value: child.student_id, label: child.nickname || child.username }))}
            onChange={(value) => { setRows([]); setText(''); setFile(null); navigate(`/parent/children/${value}/homework`) }}
          />
          {detail ? (
            <Card size="small" title={detail.title} extra={<Button onClick={() => navigate(`/parent/children/${studentId}/homework`)}>返回列表</Button>}>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="科目">{detail.subject || '未填写'}</Descriptions.Item>
                <Descriptions.Item label="截止时间">{detail.deadline ? new Date(detail.deadline).toLocaleString() : '未设置'}</Descriptions.Item>
                <Descriptions.Item label="作业要求"><div style={{ whiteSpace: 'pre-wrap' }}>{detail.description || '无'}</div></Descriptions.Item>
                <Descriptions.Item label="状态">{submitted ? <Tag color="success">已提交</Tag> : <Tag>未提交</Tag>}</Descriptions.Item>
                {record?.reviewed_at && <Descriptions.Item label="老师批改">{record.review_score ?? '未评分'} 分 {record.review_comment || ''}</Descriptions.Item>}
              </Descriptions>
              <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
                <Button loading={busy} onClick={exportPdf}>下载文字 PDF</Button>
                {submitted ? (
                  <>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{record?.text_content || '无文字作答'}</div>
                    {record?.file_url && <Button loading={busy} onClick={downloadAttachment}>下载提交附件</Button>}
                    <Alert type="success" showIcon message="已提交，不可重复提交" />
                  </>
                ) : (
                  <>
                    <Input.TextArea aria-label="作答内容" value={text} onChange={(event) => setText(event.target.value)} rows={5} placeholder="输入作答内容" />
                    <label>选择附件 <input type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
                    <label>拍照上传 <input type="file" accept="image/*" capture="environment" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
                    {file && <span>已选择：{file.name} <Button type="link" onClick={() => setFile(null)}>移除</Button></span>}
                    <Button type="primary" loading={busy} onClick={submit}>提交作业</Button>
                  </>
                )}
              </Space>
            </Card>
          ) : (
            <>
              <List loading={loading} dataSource={rows} locale={{ emptyText: '暂无作业' }} renderItem={(homework) => (
                <List.Item actions={[<Button key="detail" type="link" loading={busy} onClick={() => navigate(`/parent/children/${studentId}/homework/${homework.id}`)}>查看详情</Button>]}>
                  <List.Item.Meta title={homework.title} description={`${homework.subject || '未填写科目'} · 截止：${homework.deadline ? new Date(homework.deadline).toLocaleString() : '未设置'}`} />
                  <Tag>{homework.my_status === 'submitted' ? '已提交' : homework.my_status === 'late' ? '迟交' : homework.my_status === 'doing' ? '进行中' : '未开始'}</Tag>
                </List.Item>
              )} />
              <Pagination current={page} pageSize={10} total={total} showSizeChanger={false} onChange={setPage} />
            </>
          )}
        </Space>
      )}
    </Card>
  )
}
