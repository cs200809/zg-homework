/** admin 数据概览（PRD 5.8.5、9 admin 端）。 */

import { useEffect, useState } from 'react'
import { App, Card, Col, Row, Statistic, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'

import { statsApi } from '../../api/parent'
import type { StatsOverview } from '../../api/types'

export default function AdminDashboard() {
  const { message } = App.useApp()
  const [stats, setStats] = useState<StatsOverview | null>(null)
  const [classes, setClasses] = useState<
    {
      id: number
      name: string
      invite_code: string
      teacher_name: string | null
      student_count: number
      created_at: string
    }[]
  >([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const [s, c] = await Promise.all([statsApi.overview(), statsApi.classes(1, 5)])
        setStats(s)
        setClasses(c.list)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [message])

  if (loading || !stats) return <Card loading />

  const items = [
    { title: '用户总数', value: stats.user_count, suffix: '人' },
    { title: '启用中', value: stats.active_user_count, suffix: '人' },
    { title: '老师', value: stats.teacher_count, suffix: '人' },
    { title: '学生', value: stats.student_count, suffix: '人' },
    { title: '家长', value: stats.parent_count, suffix: '人' },
    { title: '班级', value: stats.class_count, suffix: '个' },
    { title: '作业', value: stats.homework_count, suffix: '份' },
    { title: '学生积分总量', value: stats.point_total, suffix: '分' },
  ]

  return (
    <div>
      <Row gutter={[16, 16]}>
        {items.map((it) => (
          <Col span={6} key={it.title}>
            <Card loading={loading}>
              <Statistic title={it.title} value={it.value} suffix={it.suffix} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="最近班级" style={{ marginTop: 16 }} extra={<Link to="/admin/classes">全部班级</Link>}>
        <Table
          rowKey="id"
          size="small"
          dataSource={classes}
          pagination={false}
          locale={{ emptyText: '暂无班级' }}
          columns={[
            { title: '班级', dataIndex: 'name' },
            { title: '班主任', dataIndex: 'teacher_name', render: (v: string | null) => v || '-' },
            { title: '邀请码', dataIndex: 'invite_code' },
            {
              title: '学生数',
              dataIndex: 'student_count',
              width: 100,
              render: (v: number) => <Tag>{v} 人</Tag>,
            },
          ]}
        />
      </Card>
    </div>
  )
}