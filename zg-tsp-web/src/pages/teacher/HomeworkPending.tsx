/** 老师端待批改清单（PRD 5.3）。跨作业汇总已提交但未批改的记录。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Table, Tag } from 'antd'

import ReviewModal from '../../components/ReviewModal'
import { homeworkApi } from '../../api/classes'
import type { PendingReviewRow } from '../../api/types'

export default function TeacherHomeworkPending() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<PendingReviewRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [reviewing, setReviewing] = useState<PendingReviewRow | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await homeworkApi.pending(page, 20)
      // 批改后该行不再属于待批改，最后一页可能被清空 → 回退一页
      if (r.list.length === 0 && page > 1) {
        setPage(page - 1)
        return
      }
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, message])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  return (
    <Card title="待批改">
      <Table<PendingReviewRow>
        rowKey={(r) => `${r.homework_id}-${r.student_id}`}
        dataSource={rows}
        loading={loading}
        locale={{ emptyText: '没有待批改的作业' }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: setPage,
          showSizeChanger: false,
        }}
        columns={[
          {
            title: '学生',
            dataIndex: 'student_name',
            render: (v: string, r) => (
              <span>
                {v} <span style={{ color: '#999' }}>（{r.username}）</span>
              </span>
            ),
          },
          { title: '作业', dataIndex: 'homework_title' },
          {
            title: '提交时间',
            dataIndex: 'submit_time',
            width: 170,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
          },
          {
            title: '用时(分)',
            dataIndex: 'duration_minutes',
            width: 100,
            render: (v: number | null) => (v == null ? '-' : v),
          },
          {
            title: '异常',
            dataIndex: 'suspicious',
            width: 90,
            render: (v: boolean) => (v ? <Tag color="warning">用时过短</Tag> : '-'),
          },
          {
            title: '操作',
            width: 100,
            render: (_: unknown, r) => (
              <Button size="small" onClick={() => setReviewing(r)}>
                批改
              </Button>
            ),
          },
        ]}
      />

      <ReviewModal
        open={reviewing != null}
        homeworkId={reviewing?.homework_id ?? 0}
        studentId={reviewing?.student_id ?? 0}
        studentName={reviewing?.student_name ?? ''}
        answerText={reviewing?.text_content}
        answerFileUrl={reviewing?.file_url}
        onClose={() => setReviewing(null)}
        onDone={() => setReloadKey((k) => k + 1)}
      />
    </Card>
  )
}
