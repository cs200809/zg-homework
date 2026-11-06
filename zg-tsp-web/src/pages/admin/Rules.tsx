/** admin 积分规则管理（PRD 5.8.3、9 admin 端）。 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import { EditOutlined } from '@ant-design/icons'

import { reviewRuleApi, ruleApi } from '../../api/parent'
import type { HomeworkReviewRule, PointRule } from '../../api/types'

export default function AdminRules() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<PointRule[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<PointRule | null>(null)
  const [rules, setRules] = useState<HomeworkReviewRule[]>([])
  const [creating, setCreating] = useState(false)
  const [editingRule, setEditingRule] = useState<HomeworkReviewRule | null>(null)
  // 新增与编辑各用一个 Form 实例：同一实例被两个 <Form> 复用时，
  // onFinish 与校验字段都会互相串（rc-field-form 的 setCallbacks 是实例级）。
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await ruleApi.list()
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

  const loadRules = useCallback(async () => {
    try {
      const r = await reviewRuleApi.list()
      setRules(r.list)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载批改档位失败')
    }
  }, [message])

  useEffect(() => {
    void loadRules()
  }, [loadRules])

  async function onCreateRule(values: { min_score: number; points: number }) {
    try {
      await reviewRuleApi.create(values.min_score, values.points)
      message.success('档位已新增')
      setCreating(false)
      createForm.resetFields()
      await loadRules()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '新增档位失败')
    }
  }

  async function onUpdateRule(values: { points: number; enabled: boolean }) {
    if (!editingRule) return
    try {
      await reviewRuleApi.update(editingRule.id, {
        points: values.points,
        enabled: values.enabled,
      })
      message.success('档位已更新')
      setEditingRule(null)
      editForm.resetFields()
      await loadRules()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '更新档位失败')
    }
  }

  async function onToggleRule(rule: HomeworkReviewRule) {
    try {
      await reviewRuleApi.update(rule.id, { enabled: !rule.enabled })
      await loadRules()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  function openCreateRule() {
    createForm.resetFields()
    setCreating(true)
  }

  function openEditRule(rule: HomeworkReviewRule) {
    editForm.resetFields()
    setEditingRule(rule)
    editForm.setFieldsValue({ points: rule.points, enabled: rule.enabled })
  }

  function openEditor(rule: PointRule) {
    setEditing(rule)
    form.setFieldsValue({
      points: rule.points,
      daily_limit: rule.daily_limit,
      extra_config: rule.extra_config ?? '',
      enabled: rule.enabled,
    })
  }

  async function onSave(values: {
    points: number
    daily_limit?: number | null
    extra_config?: string
    enabled: boolean
  }) {
    if (!editing) return
    try {
      await ruleApi.update({
        rule_key: editing.rule_key,
        points: values.points,
        daily_limit: values.daily_limit ?? null,
        extra_config: values.extra_config || null,
        enabled: values.enabled,
      })
      message.success('规则已更新，新的发放立即按新值执行')
      setEditing(null)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '更新失败')
    }
  }

  async function quickToggle(rule: PointRule) {
    try {
      await ruleApi.update({ rule_key: rule.rule_key, enabled: !rule.enabled })
      message.success(rule.enabled ? `已禁用「${rule.rule_name}」` : `已启用「${rule.rule_name}」`)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  return (
    <>
      <Card title="积分规则管理">
        <Table<PointRule>
          rowKey="id"
          dataSource={rows}
          loading={loading}
          pagination={false}
          locale={{ emptyText: '暂无规则' }}
          columns={[
            {
              title: '规则标识',
              dataIndex: 'rule_key',
              render: (v: string) => <code>{v}</code>,
            },
            { title: '名称', dataIndex: 'rule_name' },
            {
              title: '积分值',
              dataIndex: 'points',
              width: 100,
              render: (v: number) => <Tag color="gold">{v}</Tag>,
            },
            {
              title: '日上限',
              dataIndex: 'daily_limit',
              width: 140,
              render: (v: number | null) =>
                v == null ? (
                  <span style={{ color: '#999' }}>不限</span>
                ) : (
                  <Tooltip title="PRD 6：daily_limit 表示每天最多 N 次；游戏类为当日合计积分上限">
                    {v}
                  </Tooltip>
                ),
            },
            {
              title: '扩展配置',
              dataIndex: 'extra_config',
              render: (v: string | null) =>
                v ? (
                  <code style={{ fontSize: 12 }}>{v}</code>
                ) : (
                  <span style={{ color: '#999' }}>-</span>
                ),
            },
            {
              title: '启用',
              dataIndex: 'enabled',
              width: 100,
              render: (v: boolean, r) => (
                <Switch checked={v} onChange={() => quickToggle(r)} />
              ),
            },
            {
              title: '操作',
              width: 100,
              render: (_: unknown, r) => (
                <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(r)}>
                  编辑
                </Button>
              ),
            },
          ]}
        />

        <Modal
          title={editing ? `编辑规则：${editing.rule_name}` : ''}
          open={editing != null}
          onCancel={() => setEditing(null)}
          onOk={() => form.submit()}
          okText="保存"
          cancelText="取消"
          width={560}
        >
          <Form form={form} layout="vertical" onFinish={onSave}>
            <Form.Item label="规则标识">
              <Input value={editing?.rule_key} disabled />
            </Form.Item>
            <Form.Item
              name="points"
              label="积分值"
              rules={[{ required: true, message: '请输入积分值' }]}
              extra="每次行为获得的积分"
            >
              <InputNumber min={0} max={10000} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="daily_limit"
              label="日上限"
              extra="PRD 6：每天最多 N 次（游戏类为当日合计积分上限）；留空表示不限"
            >
              <InputNumber min={0} style={{ width: '100%' }} placeholder="留空表示不限" />
            </Form.Item>
            <Form.Item
              name="extra_config"
              label="扩展配置（JSON）"
              extra='如 {"single_article_limit":10}'
            >
              <Input.TextArea rows={3} placeholder="{}" />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Form>
        </Modal>
      </Card>

      <Card
        title="作业批改档位"
        style={{ marginTop: 16 }}
        extra={
          <Button type="primary" onClick={openCreateRule}>
            新增档位
          </Button>
        }
      >
        <Table<HomeworkReviewRule>
          rowKey="id"
          dataSource={rules}
          pagination={false}
          locale={{ emptyText: '暂无档位' }}
          columns={[
            { title: '分数下限（含）', dataIndex: 'min_score', width: 140 },
            {
              title: '积分值',
              dataIndex: 'points',
              width: 100,
              render: (v: number) => <Tag color="gold">{v}</Tag>,
            },
            {
              title: '启用',
              dataIndex: 'enabled',
              width: 100,
              render: (v: boolean, r) => (
                <Switch checked={v} onChange={() => onToggleRule(r)} />
              ),
            },
            {
              title: '操作',
              width: 100,
              render: (_: unknown, r) => (
                <Button size="small" onClick={() => openEditRule(r)}>
                  编辑
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="新增档位"
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={() => createForm.submit()}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <Form form={createForm} layout="vertical" onFinish={onCreateRule}>
          <Form.Item
            name="min_score"
            label="分数下限（含）"
            rules={[{ required: true, message: '请输入分数下限' }]}
            extra="该分数及以上命中此档；下限不可重复"
          >
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="points"
            label="积分值"
            rules={[{ required: true, message: '请输入积分值' }]}
          >
            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingRule ? `编辑档位：${editingRule.min_score} 分及以上` : ''}
        open={editingRule != null}
        onCancel={() => setEditingRule(null)}
        onOk={() => editForm.submit()}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <Form form={editForm} layout="vertical" onFinish={onUpdateRule}>
          <Form.Item name="points" label="积分值" rules={[{ required: true, message: '请输入积分值' }]}>
            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}