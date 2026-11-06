/** 老师批改作业弹窗：打分 + 评语（PRD 5.3）。完成情况页与待批改页共用。 */

import { useEffect, useState } from 'react'
import { App, Descriptions, Input, InputNumber, Modal, Space, Typography } from 'antd'

import { fileUrl } from '../api/client'
import { homeworkApi } from '../api/classes'

interface Props {
  open: boolean
  homeworkId: number
  studentId: number
  studentName: string
  initialScore?: number | null
  initialComment?: string | null
  answerText?: string | null
  answerFileUrl?: string | null
  onClose: () => void
  onDone: () => void
}

export default function ReviewModal({
  open,
  homeworkId,
  studentId,
  studentName,
  initialScore,
  initialComment,
  answerText,
  answerFileUrl,
  onClose,
  onDone,
}: Props) {
  const { message } = App.useApp()
  const [score, setScore] = useState<number>(100)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setScore(initialScore ?? 100)
    setComment(initialComment ?? '')
  }, [open, initialScore, initialComment])

  async function onSubmit() {
    setSaving(true)
    try {
      const r = await homeworkApi.review(homeworkId, studentId, score, comment.trim() || undefined)
      // 用 awarded_points（实际净变动）而非 points_delta（规则差额）：
      // 学生余额不足时实际扣减少于应扣，提示要让老师看到真实数字。
      const a = r.awarded_points
      const shortfall = r.points_delta < 0 && a > r.points_delta
      message.success(
        a > 0
          ? `批改完成，补发 ${a} 积分`
          : a < 0
            ? shortfall
              ? `批改完成，回扣 ${-a} 积分（学生余额不足，未追扣）`
              : `批改完成，回扣 ${-a} 积分`
            : '批改完成',
      )
      onDone()
      onClose()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '批改失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`批改：${studentName}`}
      open={open}
      onCancel={onClose}
      onOk={onSubmit}
      confirmLoading={saving}
      okText="提交批改"
      cancelText="取消"
      width={640}
      destroyOnClose
    >
      <Descriptions column={1} size="small" bordered style={{ marginBottom: 16 }}>
        <Descriptions.Item label="学生作答">
          <div style={{ whiteSpace: 'pre-wrap' }}>{answerText || '（无文本作答）'}</div>
        </Descriptions.Item>
        {answerFileUrl && (
          <Descriptions.Item label="附件">
            <a href={fileUrl(answerFileUrl)} target="_blank" rel="noreferrer">
              查看上传文件
            </a>
          </Descriptions.Item>
        )}
      </Descriptions>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div>
          <Typography.Text>分数（0–100）</Typography.Text>
          <InputNumber
            min={0}
            max={100}
            precision={0}
            value={score}
            onChange={(v) => setScore(v ?? 0)}
            style={{ width: 160, marginLeft: 8 }}
          />
        </div>
        <div>
          <Typography.Text>评语</Typography.Text>
          <Input.TextArea
            rows={4}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="写给学生的评语（选填）"
            maxLength={2000}
            style={{ marginTop: 8 }}
          />
        </div>
      </Space>
    </Modal>
  )
}
