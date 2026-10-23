/** 学生首页：签到、今日积分、今日作业、排行榜入口（PRD 9 学生端）。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Col, Empty, Row, Statistic, Tag } from 'antd'
import { Link } from 'react-router-dom'
import { FireOutlined, TrophyOutlined } from '@ant-design/icons'

import { checkinApi, pointsApi } from '../../api/student'
import { homeworkApi } from '../../api/classes'
import type { Homework } from '../../api/types'

const STATUS_TAG: Record<string, { color: string; text: string }> = {
  not_started: { color: 'default', text: '未开始' },
  doing: { color: 'processing', text: '进行中' },
  submitted: { color: 'success', text: '已提交' },
  late: { color: 'warning', text: '迟交' },
}

export default function StudentHome() {
  const { message } = App.useApp()
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof pointsApi.summary>> | null>(null)
  const [checkin, setCheckin] = useState<Awaited<ReturnType<typeof checkinApi.status>> | null>(null)
  const [today, setToday] = useState<Homework[]>([])
  const [rank, setRank] = useState<number>(0)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, c, h, r] = await Promise.all([
        pointsApi.summary(),
        checkinApi.status(),
        homeworkApi.today(),
        pointsApi.rank('day', 1, 50),
      ])
      setSummary(s)
      setCheckin(c)
      setToday(h.list)
      setRank(r.my_rank)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  async function onCheckin() {
    try {
      const r = await checkinApi.do()
      if (r.already_checked) {
        message.info('今天已经签到过啦')
      } else {
        const bonus = r.streak_bonus ? `，连签奖励 +${r.streak_bonus}` : ''
        message.success(`签到成功 +${r.points}${bonus}`)
      }
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '签到失败')
    }
  }

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="当前积分"
              value={summary?.total_points ?? 0}
              suffix="分"
              prefix={<TrophyOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日获得" value={summary?.gained_today ?? 0} suffix="分" />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="连续签到"
              value={checkin?.streak ?? 0}
              suffix="天"
              prefix={<FireOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日排名" value={rank > 0 ? rank : '—'} suffix={rank > 0 ? '名' : ''} />
          </Card>
        </Col>
      </Row>

      <Card
        title="每日签到"
        style={{ marginTop: 16 }}
        extra={
          <Button
            type="primary"
            disabled={checkin?.checked_in}
            loading={loading}
            onClick={onCheckin}
          >
            {checkin?.checked_in ? '今日已签到' : '签到 +5'}
          </Button>
        }
      >
        {checkin?.checked_in ? (
          <span>
            今日已签到，获得 <b>{checkin.points}</b> 分，当前连续 <b>{checkin.streak}</b> 天
          </span>
        ) : (
          <span>每天签到得 5 分，连续签到满 7 天额外奖励 10 分</span>
        )}
      </Card>

      <Card
        title="今日作业"
        style={{ marginTop: 16 }}
        extra={<Link to="/student/homework">查看全部</Link>}
      >
        {today.length === 0 ? (
          <Empty description="今天没有作业" />
        ) : (
          today.map((hw) => {
            const st = STATUS_TAG[hw.my_status ?? 'not_started']
            return (
              <div
                key={hw.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 0',
                  borderBottom: '1px solid #f0f0f0',
                }}
              >
                <div>
                  <Link to={`/student/homework/${hw.id}`}>{hw.title}</Link>
                  {hw.subject && <Tag style={{ marginLeft: 8 }}>{hw.subject}</Tag>}
                </div>
                <Tag color={st.color}>{st.text}</Tag>
              </div>
            )
          })
        )}
      </Card>
    </div>
  )
}