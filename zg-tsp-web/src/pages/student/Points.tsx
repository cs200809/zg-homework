/** 学生端我的积分（PRD 9 学生端）。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Card, Col, Row, Select, Statistic, Table, Tag } from 'antd'

import { pointsApi } from '../../api/student'
import type { PointLog, PointType } from '../../api/types'

const TYPE_LABEL: Record<PointType, string> = {
  checkin: '签到',
  homework: '作业',
  reading: '阅读',
  game: '游戏',
  consume: '消费',
  review: '作业批改',
}

const TYPE_COLOR: Record<PointType, string> = {
  checkin: 'green',
  homework: 'blue',
  reading: 'purple',
  game: 'orange',
  consume: 'red',
  review: 'cyan',
}

export default function StudentPoints() {
  const { message } = App.useApp()
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof pointsApi.summary>> | null>(null)
  const [rows, setRows] = useState<PointLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [type, setType] = useState<PointType | undefined>()
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, l] = await Promise.all([pointsApi.summary(), pointsApi.log(page, 20, type)])
      setSummary(s)
      setRows(l.list)
      setTotal(l.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, type, message])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="当前积分" value={summary?.total_points ?? 0} suffix="分" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日获得" value={summary?.gained_today ?? 0} suffix="分" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="累计获得" value={summary?.total_gained ?? 0} suffix="分" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="累计消费" value={summary?.total_consumed ?? 0} suffix="分" />
          </Card>
        </Col>
      </Row>

      <Card
        title="积分明细"
        style={{ marginTop: 16 }}
        extra={
          <Select
            allowClear
            placeholder="全部类型"
            style={{ width: 120 }}
            value={type}
            onChange={(v) => {
              setPage(1)
              setType(v)
            }}
            options={Object.entries(TYPE_LABEL).map(([k, v]) => ({ value: k, label: v }))}
          />
        }
      >
        <Table<PointLog>
          rowKey="id"
          dataSource={rows}
          loading={loading}
          locale={{ emptyText: '暂无积分记录' }}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            {
              title: '类型',
              dataIndex: 'type',
              width: 100,
              render: (v: PointType) => <Tag color={TYPE_COLOR[v]}>{TYPE_LABEL[v]}</Tag>,
            },
            {
              title: '积分',
              dataIndex: 'points',
              width: 100,
              render: (v: number) => (
                <span style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f' }}>
                  {v > 0 ? '+' : ''}
                  {v}
                </span>
              ),
            },
            { title: '说明', dataIndex: 'remark', render: (v: string | null) => v || '-' },
            {
              title: '日期',
              dataIndex: 'log_date',
              width: 120,
              render: (v: string | null) => v || '-',
            },
          ]}
        />
      </Card>
    </div>
  )
}