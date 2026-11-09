/** 学生端作业列表（PRD 9 学生端）。 */

import { useEffect, useState } from 'react'
import { Alert, App, Button, Card, Empty, List, Tabs, Tag } from 'antd'
import { Link } from 'react-router-dom'

import { homeworkApi } from '../../api/classes'
import type { Homework, HomeworkHistoryItem } from '../../api/types'

const STATUS_TAG: Record<string, { color: string; text: string }> = {
  not_started: { color: 'default', text: '未开始' },
  doing: { color: 'processing', text: '进行中' },
  submitted: { color: 'success', text: '已提交' },
  late: { color: 'warning', text: '迟交' },
}

export default function StudentHomework() {
  const { message } = App.useApp()
  const [list, setList] = useState<Homework[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const r = await homeworkApi.today()
        setList(r.list)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [message])

  const [tab, setTab] = useState('today')
  const [history, setHistory] = useState<HomeworkHistoryItem[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [historyRetry, setHistoryRetry] = useState(0)

  useEffect(() => {
    if (tab !== 'history') return
    let active = true
    setHistoryLoading(true)
    setHistoryError(false)
    homeworkApi.myList(page, 20).then((result) => {
      if (active) {
        setHistory(result.list)
        setTotal(result.total)
      }
    }).catch((e: unknown) => {
      if (active) {
        setHistoryError(true)
        message.error(e instanceof Error ? e.message : '加载失败')
      }
    }).finally(() => {
      if (active) setHistoryLoading(false)
    })
    return () => { active = false }
  }, [tab, page, message, historyRetry])

  return (
    <Card title="作业">
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'today', label: '今日作业', children: <Card loading={loading} bordered={false}>
      {list.length === 0 ? (
        <Empty description="今天没有作业" />
      ) : (
        <List
          dataSource={list}
          renderItem={(hw) => {
            const st = STATUS_TAG[hw.my_status ?? 'not_started']
            return (
              <List.Item
                actions={[<Link key="go" to={`/student/homework/${hw.id}`}>去完成</Link>]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {hw.title} {hw.subject && <Tag>{hw.subject}</Tag>}
                    </span>
                  }
                  description={`截止：${new Date(hw.deadline).toLocaleString()}`}
                />
                <Tag color={st.color}>{st.text}</Tag>
              </List.Item>
            )
          }}
        />
      )}
        </Card> },
        { key: 'history', label: '历史作业', children: historyError ? (
          <Alert
            type="error"
            message="历史作业加载失败"
            action={
              <>
                <Button onClick={() => setHistoryRetry((v) => v + 1)}>重试</Button>
                {page > 1 && <Button onClick={() => setPage(1)}>返回第一页</Button>}
              </>
            }
          />
        ) : (
          <List
            loading={historyLoading}
            dataSource={history}
            locale={{ emptyText: <Empty description="暂无已提交作业" /> }}
            pagination={{ current: page, pageSize: 20, total, onChange: setPage, showSizeChanger: false }}
            renderItem={(hw) => {
              const st = STATUS_TAG[hw.my_status ?? 'submitted']
              return (
                <List.Item actions={[<Link key="go" to={`/student/homework/${hw.id}`}>查看详情</Link>]}>
                  <List.Item.Meta
                    title={<span>{hw.title} {hw.subject && <Tag>{hw.subject}</Tag>}</span>}
                    description={
                      <span>
                        截止：{new Date(hw.deadline).toLocaleString()}<br />
                        提交：{new Date(hw.my_record.submit_time).toLocaleString()}<br />
                        批改：{hw.my_record.reviewed_at ? new Date(hw.my_record.reviewed_at).toLocaleString() : '尚未批改'}
                      </span>
                    }
                  />
                  <Tag color={st.color}>{st.text}</Tag>
                </List.Item>
              )
            }}
          />
        ) },
      ]} />
    </Card>
  )
}