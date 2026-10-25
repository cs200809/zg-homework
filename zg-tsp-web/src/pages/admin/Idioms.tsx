/** admin 成语题库管理（PRD 5.8.6、9 admin 端）。

- 批量导入（JSON 粘贴或文件上传，单次上限 1000 条）
- 同批去重；mode=skip 跳过已存在 / overwrite 覆盖
- 列表：关键词 + 启用状态筛选、分页
- 单条编辑 / 删除、批量删除
- 禁用后学生端不再抽到
 */

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Typography,
  Upload,
} from 'antd'
import { InboxOutlined, PlusOutlined } from '@ant-design/icons'

import { idiomAdminApi } from '../../api/adminIdioms'
import type { IdiomImportItem, IdiomQuestion } from '../../api/adminIdioms'

export default function AdminIdioms() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [rows, setRows] = useState<IdiomQuestion[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [enabled, setEnabled] = useState<boolean | undefined>()
  const [selected, setSelected] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [importText, setImportText] = useState('')
  const [mode, setMode] = useState<'skip' | 'overwrite'>('skip')
  const [editing, setEditing] = useState<IdiomQuestion | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await idiomAdminApi.list({
        page,
        size: 20,
        keyword: keyword.trim() || undefined,
        enabled,
      })
      setRows(r.list)
      setTotal(r.total)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, keyword, enabled, message])

  useEffect(() => {
    void load()
  }, [load])

  async function onImport() {
    let items: IdiomImportItem[]
    try {
      const parsed = JSON.parse(importText)
      const arr = Array.isArray(parsed) ? parsed : parsed.items
      if (!Array.isArray(arr)) throw new Error('格式错误')
      items = arr
    } catch (e) {
      message.error(`JSON 解析失败：${e instanceof Error ? e.message : ''}`)
      return
    }
    if (items.length === 0) {
      message.warning('没有可导入的题目')
      return
    }
    if (items.length > 1000) {
      message.error('单次最多导入 1000 条')
      return
    }

    setImporting(true)
    try {
      const r = await idiomAdminApi.import(items, mode)
      message.success(
        `导入完成：新增 ${r.success_count}、更新 ${r.updated_count}、跳过 ${r.skipped_count}` +
          (r.duplicates_in_batch > 0 ? `（同批重复 ${r.duplicates_in_batch}）` : ''),
      )
      setImportText('')
      setPage(1)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '导入失败')
    } finally {
      setImporting(false)
    }
  }

  async function onFile(file: File) {
    const text = await file.text()
    setImportText(text)
    message.info('已读取文件内容，点击「开始导入」执行')
    return false
  }

  async function onToggle(q: IdiomQuestion) {
    try {
      await idiomAdminApi.update({ question_id: q.id, enabled: !q.enabled })
      message.success(q.enabled ? '已禁用，学生端不再抽到' : '已启用')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  async function onSaveEdit(values: {
    prompt: string
    answer: string
    distractors?: string
    difficulty?: string
    enabled?: boolean
  }) {
    if (!editing) return
    try {
      await idiomAdminApi.update({
        question_id: editing.id,
        prompt: values.prompt,
        answer: values.answer,
        distractors: values.distractors
          ? values.distractors.split(/[,，\s]+/).filter(Boolean)
          : undefined,
        difficulty: values.difficulty,
        enabled: values.enabled,
      })
      message.success('已保存')
      setEditing(null)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  async function onDelete(id: number) {
    try {
      await idiomAdminApi.remove(id)
      message.success('已删除')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  async function onBatchDelete() {
    if (selected.length === 0) return
    try {
      const r = await idiomAdminApi.batchRemove(selected)
      message.success(`已删除 ${r.deleted_count} 条`)
      setSelected([])
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '批量删除失败')
    }
  }

  function openEdit(q: IdiomQuestion) {
    setEditing(q)
    form.setFieldsValue({
      prompt: q.prompt,
      answer: q.answer,
      distractors: q.distractors.join('、'),
      difficulty: q.difficulty,
      enabled: q.enabled,
    })
  }

  return (
    <Card
      title="成语题库管理"
      extra={
        <span style={{ display: 'inline-flex', gap: 8 }}>
          <Button onClick={() => setImporting(true)} icon={<PlusOutlined />}>
            批量导入
          </Button>
        </span>
      }
    >
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Input.Search
          allowClear
          placeholder="搜索题干或答案"
          style={{ width: 220 }}
          onSearch={(v) => {
            setPage(1)
            setKeyword(v)
          }}
        />
        <Select
          allowClear
          placeholder="全部状态"
          style={{ width: 130 }}
          value={enabled}
          onChange={(v) => {
            setPage(1)
            setEnabled(v)
          }}
          options={[
            { value: true, label: '启用中' },
            { value: false, label: '已禁用' },
          ]}
        />
        {selected.length > 0 && (
          <Popconfirm
            title={`确认删除选中的 ${selected.length} 条？`}
            onConfirm={onBatchDelete}
            okText="确认"
            cancelText="取消"
          >
            <Button danger>批量删除 ({selected.length})</Button>
          </Popconfirm>
        )}
      </div>

      <Table<IdiomQuestion>
        rowKey="id"
        dataSource={rows}
        loading={loading}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as number[]),
        }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: setPage,
          showSizeChanger: false,
        }}
        locale={{ emptyText: '题库为空，请批量导入' }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: '题干', dataIndex: 'prompt' },
          { title: '答案', dataIndex: 'answer' },
          {
            title: '干扰项',
            dataIndex: 'distractors',
            render: (v: string[]) =>
              v.length > 0 ? (
                <span style={{ fontSize: 12 }}>{v.join('、')}</span>
              ) : (
                <span style={{ color: '#999' }}>无</span>
              ),
          },
          {
            title: '启用',
            dataIndex: 'enabled',
            width: 90,
            render: (v: boolean, r) => <Switch checked={v} onChange={() => onToggle(r)} />,
          },
          {
            title: '操作',
            width: 140,
            render: (_: unknown, r) => (
              <>
                <Button size="small" onClick={() => openEdit(r)}>
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除该题目？"
                  onConfirm={() => onDelete(r.id)}
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

      {/* 批量导入 */}
      <Modal
        title="批量导入成语题目"
        open={importing}
        onCancel={() => setImporting(false)}
        onOk={onImport}
        okText="开始导入"
        cancelText="关闭"
        confirmLoading={importing}
        width={680}
      >
        <Typography.Paragraph type="secondary">
          粘贴 JSON 数组，或上传 JSON 文件。格式：
          <code>[{'{'}"prompt": "题干", "answer": "答案", "distractors": ["干扰1", "干扰2"]{'}'}]</code>
          <br />
          单次上限 1000 条；同批内题干自动去重；已存在的题目按下方模式处理。
        </Typography.Paragraph>

        <Upload
          accept=".json,application/json"
          beforeUpload={onFile}
          showUploadList={false}
          maxCount={1}
        >
          <Button icon={<InboxOutlined />}>选择 JSON 文件</Button>
        </Upload>

        <div style={{ margin: '12px 0' }}>
          <Select
            value={mode}
            onChange={setMode}
            options={[
              { value: 'skip', label: '已存在则跳过（skip）' },
              { value: 'overwrite', label: '已存在则覆盖（overwrite）' },
            ]}
            style={{ width: 240 }}
          />
        </div>

        <Input.TextArea
          rows={10}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder='[{"prompt": "画蛇添足", "answer": "画蛇添足"}]'
          style={{ fontFamily: 'monospace' }}
        />
      </Modal>

      {/* 编辑 */}
      <Modal
        title="编辑题目"
        open={editing != null}
        onCancel={() => setEditing(null)}
        onOk={() => form.submit()}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" onFinish={onSaveEdit}>
          <Form.Item name="prompt" label="题干" rules={[{ required: true, message: '请输入题干' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="answer" label="答案" rules={[{ required: true, message: '请输入答案' }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="distractors"
            label="干扰项"
            extra="用顿号、逗号或空格分隔，如：东、西、南"
          >
            <Input />
          </Form.Item>
          <Form.Item name="difficulty" label="难度">
            <Select
              allowClear
              options={[
                { value: 'normal', label: '普通' },
                { value: 'hard', label: '困难' },
              ]}
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
