/** 老师端作业管理：布置作业 + 列表（PRD 5.3、9 老师端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Badge,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { Link, useNavigate } from 'react-router-dom'

import { classApi, homeworkApi } from '../../api/classes'
import type { ClassInfo, Homework } from '../../api/types'

const SUBJECTS = ['语文', '数学', '英语', '科学', '道法'].map((s) => ({ value: s, label: s }))

export default function TeacherHomework() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const [classes, setClasses] = useState<ClassInfo[]>([])
  const [classId, setClassId] = useState<number | null>(null)
  const [rows, setRows] = useState<Homework[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  /** 待批改作业数（已提交未批改） */
  const [pendingCount, setPendingCount] = useState(0)

  useEffect(() => {
    ;(async () => {
      try {
        const r = await classApi.my()
        setClasses(r.classes)
        if (r.classes.length > 0) setClassId(r.classes[0].id)
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载班级失败')
      }
    })()
  }, [message])

  useEffect(() => {
    ;(async () => {
      try {
        // 只取 1 条用于探测，total 仍是全量待批改数
        const r = await homeworkApi.pending(1, 1)
        setPendingCount(r.total)
      } catch {
        // 计数失败不阻塞主流程
      }
    })()
  }, [])

  const load = useCallback(async () => {
    if (!classId) return
    setLoading(true)
    try {
      const r = await homeworkApi.list(classId, page, 20)
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [classId, page, message])

  useEffect(() => {
    void load()
  }, [load])

  async function onCreate(values: {
    title: string
    description?: string
    subject?: string
    deadline: dayjs.Dayjs
  }) {
    if (!classId) return
    try {
      await homeworkApi.create({
        class_id: classId,
        title: values.title,
        description: values.description,
        subject: values.subject,
        // 服务端要求 naive datetime（PRD 5.3），去掉时区后缀
        deadline: values.deadline.format('YYYY-MM-DDTHH:mm:ss'),
      })
      message.success('作业布置成功')
      form.resetFields()
      setPage(1)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '布置失败')
    }
  }

  async function onDelete(hw: Homework) {
    try {
      await homeworkApi.remove(hw.id)
      message.success('已删除')
      await load()
    } catch (e) {
      // 有人提交时服务端拒绝（PRD 5.3）
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  if (classes.length === 0) {
    return <Card>请先在「班级管理」创建班级</Card>
  }

  return (
    <div>
      <Card title="布置作业" style={{ marginBottom: 16 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={onCreate}
          style={{ maxWidth: 640 }}
        >
          <Form.Item name="title" label="作业标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input placeholder="如：语文作文 300 字" />
          </Form.Item>
          <Form.Item name="subject" label="科目">
            <Select allowClear options={SUBJECTS} placeholder="选择科目" />
          </Form.Item>
          <Form.Item name="description" label="作业要求">
            <Input.TextArea rows={3} placeholder="选填" />
          </Form.Item>
          <Form.Item
            name="deadline"
            label="截止时间"
            rules={[{ required: true, message: '请选择截止时间' }]}
          >
            <DatePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
              disabledDate={(d) => d.isBefore(dayjs(), 'day')}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>
              布置作业
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card
        title="作业列表"
        extra={
          <Space>
            <Badge count={pendingCount} overflowCount={99}>
              <Button onClick={() => navigate('/teacher/homework/pending')}>待批改</Button>
            </Badge>
            <Select
              style={{ width: 180 }}
              value={classId}
              onChange={(v) => {
                setClassId(v)
                setPage(1)
              }}
              options={classes.map((c) => ({ value: c.id, label: c.name }))}
            />
          </Space>
        }
      >
        <Table<Homework>
          rowKey="id"
          dataSource={rows}
          loading={loading}
          locale={{ emptyText: '还没有布置作业' }}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: setPage,
            showSizeChanger: false,
          }}
          columns={[
            {
              title: '标题',
              dataIndex: 'title',
              render: (v: string, r) => (
                <Link to={`/teacher/homework/${r.id}`}>
                  {v} {r.subject && <Tag>{r.subject}</Tag>}
                </Link>
              ),
            },
            {
              title: '截止时间',
              dataIndex: 'deadline',
              render: (v: string) => (
                <Tag color={dayjs(v).isBefore(dayjs()) ? 'red' : 'default'}>
                  {new Date(v).toLocaleString()}
                </Tag>
              ),
            },
            {
              title: '操作',
              width: 160,
              render: (_: unknown, r) => (
                <>
                  <Button size="small" onClick={() => navigate(`/teacher/homework/${r.id}`)}>
                    完成情况
                  </Button>
                  <Popconfirm
                    title="确认删除该作业？"
                    description="已有学生提交时不可删除"
                    onConfirm={() => onDelete(r)}
                    okText="确认"
                    cancelText="取消"
                  >
                    <Button size="small" danger style={{ marginLeft: 8 }}>
                      删除
                    </Button>
                  </Popconfirm>
                </>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}