/**
 * 学生端作业详情：开始/提交（PRD 5.3、9 学生端）。
 *
 * 时间采集由服务端负责：
 * - 「开始写作业」调用 /homework/start，重复点击服务端不覆盖首次时间
 * - 「提交作业」调用 /homework/submit，服务端算用时、判迟交、发积分
 */

import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Result,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'

import { homeworkApi } from '../../api/classes'
import { fileUrl } from '../../api/client'
import type { Homework } from '../../api/types'

export default function StudentHomeworkDetail() {
  const { id } = useParams()
  const homeworkId = Number(id)
  const { message } = App.useApp()

  const [hw, setHw] = useState<Homework | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)

  async function load() {
    setLoading(true)
    try {
      const r = await homeworkApi.detail(homeworkId)
      setHw(r.homework)
      if (r.homework.my_record?.text_content) setText(r.homework.my_record.text_content)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (Number.isFinite(homeworkId)) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeworkId])

  async function onStart() {
    try {
      const r = await homeworkApi.start(homeworkId)
      message.success(r.already_started ? '已开始过了，继续完成吧' : '开始计时')
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  async function onSubmit() {
    if (!text.trim() && !file) {
      message.warning('请填写内容或上传文件')
      return
    }
    setSubmitting(true)
    try {
      const r = await homeworkApi.submit(homeworkId, { textContent: text, file })
      message.success(`提交成功，获得 ${r.record.points} 积分`)
      await load()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!hw) {
    return <Result status="404" title="作业不存在" />
  }

  const rec = hw.my_record
  const submitted = rec?.submit_time != null

  return (
    <Card
      title={hw.title}
      extra={
        <Space>
          {!rec?.start_time && !submitted && (
            <Button type="primary" onClick={onStart}>
              开始写作业
            </Button>
          )}
        </Space>
      }
    >
      <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="科目">{hw.subject || '未填写'}</Descriptions.Item>
        <Descriptions.Item label="截止时间">
          {new Date(hw.deadline).toLocaleString()}
        </Descriptions.Item>
        <Descriptions.Item label="作业要求">
          <div style={{ whiteSpace: 'pre-wrap' }}>{hw.description || '无'}</div>
        </Descriptions.Item>
        {rec?.start_time && (
          <Descriptions.Item label="开始时间">
            {new Date(rec.start_time).toLocaleString()}
          </Descriptions.Item>
        )}
        {submitted && (
          <Descriptions.Item label="提交信息">
            <Space direction="vertical" size={0}>
              <span>提交时间：{new Date(rec.submit_time!).toLocaleString()}</span>
              <span>用时：{rec.duration_minutes} 分钟</span>
              <span>
                状态：<Tag color={rec.status === 'late' ? 'warning' : 'success'}>{rec.status === 'late' ? '迟交' : '已提交'}</Tag>
                积分：{rec.points} 分
              </span>
            </Space>
          </Descriptions.Item>
        )}
      </Descriptions>

      {rec?.suspicious && !rec.reviewed_at && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="本次用时不足 1 分钟，已标记待老师审核"
        />
      )}

      {rec?.reviewed_at ? (
        <Card size="small" title="老师批改" style={{ marginBottom: 16 }}>
          <Space align="start" size={24} wrap>
            <Statistic
              title="分数"
              value={rec.review_score ?? 0}
              suffix="分"
              valueStyle={{
                fontSize: 28,
                color:
                  (rec.review_score ?? 0) >= 90
                    ? '#52c41a'
                    : (rec.review_score ?? 0) >= 60
                      ? '#fa8c16'
                      : '#f5222d',
              }}
            />
            <Statistic title="批改积分" value={rec.review_points ?? 0} suffix="分" />
            <div style={{ flex: 1, minWidth: 240 }}>
              <Typography.Text type="secondary">评语</Typography.Text>
              <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>
                {rec.review_comment || '老师未写评语'}
              </div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                批改时间：{new Date(rec.reviewed_at).toLocaleString()}
              </Typography.Text>
            </div>
          </Space>
        </Card>
      ) : submitted ? (
        <Alert type="info" showIcon message="老师尚未批改" style={{ marginBottom: 16 }} />
      ) : null}

      {submitted ? (
        <>
          <Card size="small" title="我的作答" style={{ marginBottom: 16 }}>
            <div style={{ whiteSpace: 'pre-wrap' }}>{rec.text_content || '无文字作答'}</div>
            {rec.file_url && (
              <a href={fileUrl(rec.file_url)} target="_blank" rel="noreferrer">查看附件</a>
            )}
          </Card>
          <Alert type="success" showIcon message="已提交，不可重复提交" />
        </>
      ) : (
        <>
          <label>我的作答</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="在这里输入答案"
            style={{
              width: '100%',
              minHeight: 160,
              marginTop: 8,
              padding: 8,
              border: '1px solid #d9d9d9',
              borderRadius: 6,
            }}
          />
          <Space style={{ marginTop: 16 }} wrap>
            <Upload
              maxCount={1}
              beforeUpload={(f) => {
                setFile(f)
                return false
              }}
              onRemove={() => setFile(null)}
              fileList={file ? [{ uid: '1', name: file.name }] : []}
            >
              <Button icon={<UploadOutlined />}>
                {file ? '已选择文件' : '上传文件（选填）'}
              </Button>
            </Upload>
            <Button
              type="primary"
              loading={submitting}
              disabled={!rec?.start_time}
              onClick={onSubmit}
            >
              {rec?.start_time ? '提交作业' : '请先点击「开始写作业」'}
            </Button>
          </Space>
        </>
      )}
    </Card>
  )
}