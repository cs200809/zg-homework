/** 学生端排行榜：日榜 / 总榜（PRD 5.4）。 */

import { useEffect, useState } from 'react'
import { App, Card, Table, Tabs, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'

import { pointsApi } from '../../api/student'
import type { RankItem } from '../../api/types'

function RankTable({ type }: { type: 'day' | 'total' }) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [rows, setRows] = useState<RankItem[]>([])
  const [myRank, setMyRank] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      setLoading(true)
      try {
        const r = await pointsApi.rank(type, 1, 50)
        setRows(r.list)
        setMyRank(r.my_rank)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [type, message])

  return (
    <>
      {myRank > 0 && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Typography.Text>
            我的排名：<Tag color="gold">第 {myRank} 名</Tag>
            {myRank > 50 && <span style={{ marginLeft: 8 }}>（不在前 50，继续加油）</span>}
          </Typography.Text>
        </Card>
      )}

      <Table<RankItem>
        rowKey="user_id"
        dataSource={rows}
        loading={loading}
        pagination={false}
        locale={{ emptyText: '暂无排行数据' }}
        onRow={() => ({
          onClick: () => navigate('/student/points'),
          style: { cursor: 'pointer' },
        })}
        columns={[
          {
            title: '名次',
            dataIndex: 'rank',
            width: 80,
            render: (v: number) =>
              v <= 3 ? <Tag color={['gold', 'silver', 'bronze'][v - 1]}>{v}</Tag> : v,
          },
          {
            title: '昵称',
            dataIndex: 'nickname',
            render: (v: string | null, r) => v || r.username,
          },
          { title: '积分', dataIndex: 'points', width: 100 },
        ]}
      />
    </>
  )
}

export default function StudentRank() {
  return (
    <Card title="排行榜">
      <Tabs
        items={[
          { key: 'day', label: '今日榜', children: <RankTable type="day" /> },
          { key: 'total', label: '总榜', children: <RankTable type="total" /> },
        ]}
      />
    </Card>
  )
}