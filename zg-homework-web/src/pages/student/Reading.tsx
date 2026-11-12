/** 学生端阅读列表（PRD 9 学生端）。 */

import { useEffect, useState } from 'react'
import { App, Card, Empty, List, Tag } from 'antd'
import { Link } from 'react-router-dom'

import { articleApi } from '../../api/student'
import type { Article } from '../../api/types'

export default function StudentReading() {
  const { message } = App.useApp()
  const [list, setList] = useState<Article[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const r = await articleApi.list(1, 50)
        setList(r.list)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [message])

  return (
    <Card title="课后阅读" loading={loading}>
      {list.length === 0 ? (
        <Empty description="暂无文章" />
      ) : (
        <List
          dataSource={list}
          renderItem={(a) => (
            <List.Item
              actions={[<Link key="go" to={`/student/reading/${a.id}`}>开始阅读</Link>]}
            >
              <List.Item.Meta
                title={a.title}
                description={`发布者角色：${a.created_role === 'admin' ? '管理员' : '老师'}`}
              />
              {a.my_record?.finished ? <Tag color="success">已读完</Tag> : null}
            </List.Item>
          )}
        />
      )}
    </Card>
  )
}