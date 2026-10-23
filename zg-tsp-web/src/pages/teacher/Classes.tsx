/** 老师端班级管理（PRD 5.2、9 老师端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Table,
  Tag,
  Typography,
} from 'antd'
import { CopyOutlined, PlusOutlined } from '@ant-design/icons'

import { classApi } from '../../api/classes'
import type { ClassInfo, ClassStudent } from '../../api/types'

export default function TeacherClasses() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [classes, setClasses] = useState<ClassInfo[]>([])
  const [current, setCurrent] = useState<ClassInfo | null>(null)
  const [students, setStudents] = useState<ClassStudent[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await classApi.my()
      setClasses(r.classes)
      setCurrent(r.classes.length > 0 ? r.classes[0] : null)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  const loadStudents = useCallback(
    async (klass: ClassInfo) => {
      try {
        const r = await classApi.students(klass.id)
        setStudents(r.students)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载学生失败')
      }
    },
    [message],
  )

  useEffect(() => {
    if (current) void loadStudents(current)
  }, [current, loadStudents])

  async function onCreate(values: { name: string }) {
    try {
      const r = await classApi.create(values.name)
      message.success(`班级创建成功，邀请码：${r.class.invite_code}`)
      form.resetFields()
      await load()
      setCurrent(r.class)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '创建失败')
    }
  }

  async function onRemove(student: ClassStudent) {
    if (!current) return
    try {
      await classApi.removeStudent(current.id, student.id)
      message.success(`已移除 ${student.nickname || student.username}`)
      await loadStudents(current)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '移除失败')
    }
  }

  function copyCode(code: string) {
    // 复制失败时降级为提示，避免用户看不到邀请码
    navigator.clipboard
      ?.writeText(code)
      .then(() => message.success('邀请码已复制'))
      .catch(() => message.warning(`复制失败，请手动记录：${code}`))
  }

  return (
    <div>
      <Card title="我的班级" loading={loading} style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={onCreate} style={{ marginBottom: 16 }}>
          <Form.Item name="name" rules={[{ required: true, message: '请输入班级名称' }]}>
            <Input placeholder="新班级名称" style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<PlusOutlined />} htmlType="submit">
              创建班级
            </Button>
          </Form.Item>
        </Form>

        {classes.length === 0 ? (
          <Typography.Text type="secondary">还没有班级，请先创建</Typography.Text>
        ) : (
          <Table<ClassInfo>
            rowKey="id"
            size="small"
            dataSource={classes}
            pagination={false}
            rowClassName={(r) => (r.id === current?.id ? 'ant-table-row-selected' : '')}
            onRow={(r) => ({
              onClick: () => setCurrent(r),
              style: { cursor: 'pointer' },
            })}
            columns={[
              { title: '班级名称', dataIndex: 'name' },
              {
                title: '邀请码',
                dataIndex: 'invite_code',
                render: (v: string) => (
                  <Button
                    type="link"
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      copyCode(v)
                    }}
                  >
                    {v}
                  </Button>
                ),
              },
              {
                title: '学生数',
                dataIndex: 'student_count',
                width: 100,
                render: (v: number | null) => v ?? 0,
              },
            ]}
          />
        )}
      </Card>

      {current && (
        <Card title={`${current.name} · 学生名单`}>
          <Table<ClassStudent>
            rowKey="id"
            size="small"
            dataSource={students}
            pagination={false}
            locale={{ emptyText: '暂无学生，请同学使用邀请码加入' }}
            columns={[
              {
                title: '昵称',
                dataIndex: 'nickname',
                render: (v: string | null, r: ClassStudent) => v || r.username,
              },
              { title: '用户名', dataIndex: 'username' },
              {
                title: '积分',
                dataIndex: 'total_points',
                width: 100,
                render: (v: number) => <Tag color="gold">{v} 分</Tag>,
              },
              {
                title: '操作',
                width: 100,
                render: (_: unknown, r: ClassStudent) => (
                  <Popconfirm
                    title="确认移出该学生？"
                    onConfirm={() => onRemove(r)}
                    okText="确认"
                    cancelText="取消"
                  >
                    <Button danger size="small">
                      移出
                    </Button>
                  </Popconfirm>
                ),
              },
            ]}
          />
        </Card>
      )}
    </div>
  )
}