/** 家长端：孩子积分明细 + 积分消耗（PRD 5.7、9 家长端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  AutoComplete,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Statistic,
  Table,
  Tag,
} from 'antd'
import { MinusCircleOutlined, PlusCircleOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'

import { parentApi } from '../../api/parent'
import type { ConsumeItem, PointLog } from '../../api/types'

const TYPE_LABEL: Record<string, string> = {
  checkin: '签到',
  homework: '作业',
  reading: '阅读',
  game: '游戏',
  consume: '消费',
  parent_reward: '家长奖励',
}

export default function ParentChildPoints() {
  const { id } = useParams()
  const studentId = Number(id)
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rewardForm] = Form.useForm()
  const [rewardItems, setRewardItems] = useState<ConsumeItem[]>([])
  const [rewarding, setRewarding] = useState(false)
  const [submittingReward, setSubmittingReward] = useState(false)

  const [student, setStudent] = useState<{
    id: number
    nickname: string | null
    total_points: number
  } | null>(null)
  const [summary, setSummary] = useState<{
    total_points: number
    gained_today: number
    total_gained: number
    total_consumed: number
  } | null>(null)
  const [rows, setRows] = useState<PointLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  const [items, setItems] = useState<ConsumeItem[]>([])
  const [consuming, setConsuming] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await parentApi.childPoints(studentId, page, 20)
      setStudent(r.student)
      setSummary(r.summary)
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [studentId, page, message])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    ;(async () => {
      try {
        const r = await parentApi.consumeItems()
        setItems(r.list)
      } catch {
        // 预设事项加载失败不阻断主流程
      }
    })()
  }, [])

  useEffect(() => {
    parentApi.rewardItems().then((r) => setRewardItems(r.list)).catch(() => {
      // 预设加载失败时仍可自定义奖励
    })
  }, [])

  function openReward(preset?: ConsumeItem) {
    rewardForm.resetFields()
    rewardForm.setFieldsValue({ item: preset?.name, points: preset?.points })
    setRewarding(true)
  }

  async function onReward(values: { item: string; points: number; remark?: string }) {
    if (submittingReward) return
    setSubmittingReward(true)
    try {
      await parentApi.reward(studentId, values.item.trim(), values.points, values.remark?.trim())
      message.success('奖励积分成功')
      setRewarding(false)
      rewardForm.resetFields()
      if (page === 1) await load()
      else setPage(1)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '奖励积分失败')
    } finally {
      setSubmittingReward(false)
    }
  }

  function openConsume(preset?: ConsumeItem) {
    form.setFieldsValue({
      item: preset?.name,
      points: preset?.points,
      remark: '',
    })
    setConsuming(true)
  }

  async function onConsume(values: { item: string; points: number; remark?: string }) {
    try {
      const r = await parentApi.consume(studentId, values.item, values.points, values.remark)
      message.success(`已扣减 ${r.points} 分，剩余 ${r.total_points} 分`)
      setConsuming(false)
      form.resetFields()
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '扣分失败')
    }
  }

  return (
    <div>
      <Card
        title={student ? `${student.nickname || '孩子'} 的积分` : '孩子积分'}
        loading={loading}
        extra={
          <>
            <Button icon={<PlusCircleOutlined />} onClick={() => openReward()} style={{ marginRight: 8 }}>
              奖励积分
            </Button>
            <Button type="primary" danger icon={<MinusCircleOutlined />} onClick={() => openConsume()}>
              积分消耗
            </Button>
          </>
        }
      >
        <Row gutter={16}>
          <Col span={6}>
            <Statistic title="当前余额" value={summary?.total_points ?? 0} suffix="分" />
          </Col>
          <Col span={6}>
            <Statistic title="今日获得" value={summary?.gained_today ?? 0} suffix="分" />
          </Col>
          <Col span={6}>
            <Statistic title="累计获得" value={summary?.total_gained ?? 0} suffix="分" />
          </Col>
          <Col span={6}>
            <Statistic title="累计消费" value={summary?.total_consumed ?? 0} suffix="分" />
          </Col>
        </Row>
      </Card>

      <Card title="快速消耗" style={{ marginTop: 16 }}>
        <span style={{ marginRight: 8 }}>预设事项：</span>
        {items.map((it) => (
          <Button
            key={it.key}
            onClick={() => openConsume(it)}
            disabled={summary != null && it.points > summary.total_points}
            style={{ marginRight: 8 }}
          >
            {it.name} -{it.points}
          </Button>
        ))}
      </Card>

      <Card title="快速奖励" style={{ marginTop: 16 }}>
        <span style={{ marginRight: 8 }}>预设事项：</span>
        {rewardItems.map((it) => (
          <Button key={it.key} onClick={() => openReward(it)} style={{ marginRight: 8 }}>
            {it.name} +{it.points}
          </Button>
        ))}
        {rewardItems.length === 0 && <span>暂无预设，可使用奖励积分自定义事项</span>}
      </Card>

      <Card title="积分明细" style={{ marginTop: 16 }}>
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
              width: 90,
              render: (v: string) => <Tag>{TYPE_LABEL[v] ?? v}</Tag>,
            },
            {
              title: '积分',
              dataIndex: 'points',
              width: 90,
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

      <Modal
        title="奖励积分"
        open={rewarding}
        onCancel={() => setRewarding(false)}
        onOk={() => rewardForm.submit()}
        okText="确认奖励"
        cancelText="取消"
        confirmLoading={submittingReward}
        maskClosable={!submittingReward}
        keyboard={!submittingReward}
        cancelButtonProps={{ disabled: submittingReward }}
        closable={!submittingReward}
      >
        <Form form={rewardForm} layout="vertical" onFinish={onReward}>
          <Form.Item
            name="item"
            label="事项"
            rules={[
              { required: true, whitespace: true, message: '请输入事项' },
              { max: 50, message: '事项不能超过 50 个字符' },
            ]}
          >
            <AutoComplete
              options={rewardItems.map((i) => ({ value: i.name, label: `${i.name} (+${i.points})` }))}
              placeholder="选择预设事项，或输入自定义事项"
              filterOption={(input, option) =>
                String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
              }
              onSelect={(value) => {
                const item = rewardItems.find((i) => i.name === value)
                if (item) rewardForm.setFieldValue('points', item.points)
              }}
            >
              <Input maxLength={50} />
            </AutoComplete>
          </Form.Item>
          <Form.Item
            name="points"
            label="奖励分数"
            rules={[
              { required: true, message: '请输入奖励分数' },
              { type: 'number', min: 1, max: 10000, message: '请输入 1 至 10000 的整数' },
              { validator: (_, value) => value == null || Number.isInteger(value) ? Promise.resolve() : Promise.reject(new Error('请输入整数')) },
            ]}
          >
            <InputNumber min={1} max={10000} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="remark"
            label="备注（选填）"
            dependencies={['item']}
            rules={[({ getFieldValue }) => ({
              validator(_, value: string | undefined) {
                const item = String(getFieldValue('item') || '').trim()
                const remark = value?.trim() || ''
                return item.length + (remark ? 1 + remark.length : 0) <= 255
                  ? Promise.resolve()
                  : Promise.reject(new Error('事项和备注合计不能超过 255 个字符'))
              },
            })]}
          >
            <Input placeholder="填写奖励备注" maxLength={255} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="积分消耗"
        open={consuming}
        onCancel={() => setConsuming(false)}
        onOk={() => form.submit()}
        okText="确认扣减"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <Form form={form} layout="vertical" onFinish={onConsume}>
          <Form.Item name="item" label="事项" rules={[{ required: true, message: '请输入事项' }]}>
            {/* PRD 5.7：预设事项之外还支持自定义，因此用 Select 的
                showSearch + 自由输入（不限制 options）实现 */}
            <Select
              showSearch
              options={items.map((i) => ({ value: i.name, label: `${i.name} (-${i.points})` }))}
              placeholder="选择预设事项，或直接输入自定义事项"
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item
            name="points"
            label="扣减分数"
            rules={[{ required: true, message: '请输入扣减分数' }]}
            extra={
              summary != null && (
                <span>当前余额 {summary.total_points} 分</span>
              )
            }
          >
            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label="备注（选填）">
            <Input placeholder="如：玩了 30 分钟手机" maxLength={255} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}