/** 家长端：孩子列表 + 绑定（PRD 5.7、9 家长端）。 */

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, Empty, Form, Input, List, Modal, Popconfirm, Tag } from 'antd'
import { Link } from 'react-router-dom'
import { PlusOutlined } from '@ant-design/icons'

import { parentApi } from '../../api/parent'
import type { Child } from '../../api/types'

export default function ParentChildren() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<Child[]>([])
  const [loading, setLoading] = useState(true)
  const [binding, setBinding] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await parentApi.children()
      setRows(r.list)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  async function onBind(values: { bind_code: string }) {
    try {
      const r = await parentApi.bind(values.bind_code)
      message.success(`已绑定 ${r.nickname || r.username}`)
      form.resetFields()
      setBinding(false)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '绑定失败')
    }
  }

  async function onUnbind(child: Child) {
    try {
      await parentApi.unbind(child.student_id)
      message.success('已解绑')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '解绑失败')
    }
  }

  return (
    <Card
      title="我的孩子"
      loading={loading}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setBinding(true)}>
          绑定孩子
        </Button>
      }
    >
      {rows.length === 0 ? (
        <Empty description="还没有绑定孩子，请让孩子在他的个人中心获取绑定码" />
      ) : (
        <List
          dataSource={rows}
          renderItem={(c) => (
            <List.Item
              actions={[
                <Link key="points" to={`/parent/children/${c.student_id}`}>
                  积分明细
                </Link>,
                <Popconfirm
                  key="unbind"
                  title="确认解除绑定？"
                  description="解绑后将无法查看与扣减其积分"
                  onConfirm={() => onUnbind(c)}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button size="small" danger>
                    解绑
                  </Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={c.nickname || c.username}
                description={`用户名：${c.username}`}
              />
              <Tag color="gold">{c.total_points} 分</Tag>
            </List.Item>
          )}
        />
      )}

      <Modal
        title="绑定孩子"
        open={binding}
        onCancel={() => setBinding(false)}
        onOk={() => form.submit()}
        okText="绑定"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={onBind}>
          <Form.Item
            name="bind_code"
            label="孩子绑定码"
            rules={[{ required: true, message: '请输入绑定码' }]}
          >
            <Input placeholder="让孩子在个人中心查看绑定码" maxLength={8} />
          </Form.Item>
        </Form>
        <p style={{ color: '#999', marginBottom: 0 }}>
          绑定码由学生账号生成，在学生端「我的」页面查看。
        </p>
      </Modal>
    </Card>
  )
}