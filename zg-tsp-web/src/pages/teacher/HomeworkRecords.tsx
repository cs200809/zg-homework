/** 老师端作业完成情况（PRD 5.3、9 老师端）。 */

import { useEffect, useState } from 'react'
import { App, Card, Descriptions, Statistic, Table, Tag, Typography } from 'antd'
import { useParams } from 'react-router-dom'

import { homeworkApi } from '../../api/classes'
import type { Homework, HomeworkRecordRow, HomeworkStatus } from '../../api/types'

const STATUS_TAG: Record<HomeworkStatus, { color: string; text: string }> = {
  not_started: { color: 'default', text: '未开始' },
  doing: { color: 'processing', text: '进行中' },
  submitted: { color: 'success', text: '已提交' },
  late: { color: 'warning', text: '迟交' },
}

export default function TeacherHomeworkRecords() {
  const { id } = useParams()
  const homeworkId = Number(id)
  const { message } = App.useApp()

  const [hw, setHw] = useState<Homework | null>(null)
  const [rows, setRows] = useState<HomeworkRecordRow[]>([])
  const [submitted, setSubmitted] = useState(0)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!Number.isFinite(homeworkId)) return
    ;(async () => {
      try {
        const r = await homeworkApi.records(homeworkId)
        setHw(r.homework)
        setRows(r.records)
        setSubmitted(r.submitted_count)
        setTotal(r.total_students)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [homeworkId, message])

  if (loading) {
    return <Card loading />
  }
  if (!hw) {
    return <Card>作业不存在</Card>
  }

  return (
    <div>
      <Card title={`${hw.title} · 完成情况`} style={{ marginBottom: 16 }}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="科目">{hw.subject || '-'}</Descriptions.Item>
          <Descriptions.Item label="截止时间">
            {new Date(hw.deadline).toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="提交率">
            {total > 0 ? Math.round((submitted / total) * 100) : 0}%（{submitted}/{total}）
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card>
        <Table<HomeworkRecordRow>
          rowKey="student_id"
          dataSource={rows}
          pagination={false}
          locale={{ emptyText: '本班暂无学生' }}
          columns={[
            {
              title: '学生',
              dataIndex: 'nickname',
              render: (v: string | null, r) => v || r.username,
            },
            { title: '用户名', dataIndex: 'username' },
            {
              title: '状态',
              dataIndex: 'status',
              width: 100,
              render: (v: HomeworkStatus) => {
                const tag = STATUS_TAG[v] ?? { color: 'default', text: v }
                return <Tag color={tag.color}>{tag.text}</Tag>
              },
            },
            {
              title: '开始时间',
              dataIndex: 'start_time',
              width: 160,
              render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
            },
            {
              title: '提交时间',
              dataIndex: 'submit_time',
              width: 160,
              render: (v: string | null) => (v ? new Date(v).toLocaleString() : '-'),
            },
            {
              title: '用时(分)',
              dataIndex: 'duration_minutes',
              width: 100,
              render: (v: number | null, r: HomeworkRecordRow) => {
                if (v == null) return '-'
                return (
                  <span>
                    {v}
                    {r.suspicious && (
                      <Typography.Text type="warning" style={{ marginLeft: 4 }}>
                        ⚠ 待审核
                      </Typography.Text>
                    )}
                  </span>
                )
              },
            },
            {
              title: '积分',
              dataIndex: 'points',
              width: 80,
              render: (v: number) => <Tag color="gold">{v}</Tag>,
            },
          ]}
        />
      </Card>

      <Card style={{ marginTop: 16 }} size="small">
        <Statistic
          title="已提交（含迟交）"
          value={submitted}
          suffix={` / ${total} 人`}
        />
      </Card>
    </div>
  )
}