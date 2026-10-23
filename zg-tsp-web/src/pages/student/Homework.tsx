/** 学生端作业列表（PRD 9 学生端）。 */

import { useEffect, useState } from 'react'
import { App, Card, Empty, List, Tag } from 'antd'
import { Link } from 'react-router-dom'

import { homeworkApi } from '../../api/classes'
import type { Homework } from '../../api/types'

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

  return (
    <Card title="今日作业" loading={loading}>
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
    </Card>
  )
}