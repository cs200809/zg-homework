/** admin 班级总览（PRD 5.8.5、9 admin 端）。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Card, Table, Typography } from 'antd'

import { statsApi } from '../../api/parent'
import type { PageResult } from '../../api/classes'

type ClassRow = {
  id: number
  name: string
  invite_code: string
  teacher_name: string | null
  student_count: number
  created_at: string
}

export default function AdminClasses() {
  const { message } = App.useApp()
  const [rows, setRows] = useState<ClassRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r: PageResult<ClassRow> = await statsApi.classes(page, 20)
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
  }, [load])

  return (
    <Card title="班级总览">
      <Table<ClassRow>
        rowKey="id"
        dataSource={rows}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: setPage,
          showSizeChanger: false,
        }}
        locale={{ emptyText: '暂无班级' }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '班级名称', dataIndex: 'name' },
          { title: '班主任', dataIndex: 'teacher_name', render: (v: string | null) => v || '-' },
          {
            title: '邀请码',
            dataIndex: 'invite_code',
            render: (v: string) => <Typography.Text copyable>{v}</Typography.Text>,
          },
          { title: '学生数', dataIndex: 'student_count', width: 100 },
          {
            title: '创建时间',
            dataIndex: 'created_at',
            width: 170,
            render: (v: string) => new Date(v).toLocaleString(),
          },
        ]}
      />
    </Card>
  )
}