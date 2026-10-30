/**
 * 学生端文章阅读页（PRD 5.5）。
 *
 * 防挂机机制（PRD 5.5）：
 * - 进入页面开始计时，**切到后台暂停**（监听 visibilitychange）
 * - 每 30 秒上报一次心跳；服务端校验间隔 30s±10s，异常不计分
 * - 滚动到底触发「读完」标记，+5 分（单篇仅一次）
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, App, Button, Card, Result, Space, Spin, Tag, Typography } from 'antd'
import { useParams } from 'react-router-dom'

import { fileUrl } from '../../api/client'
import { articleApi } from '../../api/student'
import type { Article } from '../../api/types'

/** 心跳间隔：与 PRD 5.5 一致（服务端容差 ±10s） */
const HEARTBEAT_MS = 30_000

export default function StudentArticle() {
  const { id } = useParams()
  const articleId = Number(id)
  const { message } = App.useApp()

  const [article, setArticle] = useState<Article | null>(null)
  const [loading, setLoading] = useState(true)
  const [elapsed, setElapsed] = useState(0)
  const [points, setPoints] = useState(0)
  const [finished, setFinished] = useState(false)

  const bodyRef = useRef<HTMLDivElement>(null)
  /** 可见且在滚动范围内时才算有效阅读时长 */
  const activeRef = useRef(false)

  // 加载文章
  useEffect(() => {
    if (!Number.isFinite(articleId)) return
    ;(async () => {
      try {
        const r = await articleApi.detail(articleId)
        setArticle(r.article)
        if (r.article.my_record) {
          setElapsed(r.article.my_record.duration_seconds)
          setPoints(r.article.my_record.points)
          setFinished(r.article.my_record.finished)
        }
      } catch (e) {
        message.error(e instanceof Error ? e.message : '加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [articleId, message])

  // 页面可见性：切后台暂停计时（PRD 5.5）
  useEffect(() => {
    const onVisibility = () => {
      activeRef.current = document.visibilityState === 'visible'
    }
    document.addEventListener('visibilitychange', onVisibility)
    activeRef.current = document.visibilityState === 'visible'
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  // 心跳：每 30 秒上报一次
  const report = useCallback(async () => {
    if (!activeRef.current) return // 切后台不上报，避免被判为挂机
    try {
      const r = await articleApi.heartbeat(articleId, HEARTBEAT_MS / 1000)
      setElapsed(r.duration_seconds)
      setPoints(r.points)
      if (!r.accepted) {
        message.warning(r.reason || '本次计时未被采纳')
      } else if (r.points_gained) {
        message.success(`阅读 +${r.points_gained} 分`)
      }
    } catch {
      // 网络异常时静默，等下一个心跳
    }
  }, [articleId, message])

  useEffect(() => {
    if (!Number.isFinite(articleId)) return
    const timer = setInterval(report, HEARTBEAT_MS)
    return () => clearInterval(timer)
  }, [articleId, report])

  // 本地秒表，仅用于展示
  useEffect(() => {
    const t = setInterval(() => {
      if (activeRef.current) setElapsed((v) => v + 1)
    }, 1000)
    return () => clearInterval(t)
  }, [])

  // 滚动到底 → 标记读完（+5 分，单篇一次）
  async function onReachBottom() {
    if (finished) return
    try {
      const r = await articleApi.finish(articleId)
      if (r.already_finished) {
        setFinished(true)
      } else {
        setPoints(r.points)
        setFinished(true)
        message.success(`恭喜读完本篇，获得 ${r.points_gained} 积分`)
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <Spin size="large" />
      </div>
    )
  }
  if (!article) return <Result status="404" title="文章不存在或已下架" />

  const minutes = Math.floor(elapsed / 60)
  const seconds = elapsed % 60

  return (
    <Card
      title={article.title}
      extra={
        <Space>
          <Tag color="blue">
            已阅读 {minutes}:{String(seconds).padStart(2, '0')}
          </Tag>
          <Tag color="gold">{points} 分</Tag>
          {finished && <Tag color="success">已读完</Tag>}
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="每阅读满 1 分钟得 1 分，单篇最多 10 分、每日最多 30 分；读完再得 5 分"
        description="阅读计时仅在页面处于前台时累计，切换到后台会自动暂停。"
      />

      <div
        ref={bodyRef}
        style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, minHeight: 320 }}
      >
        {article.content}
      </div>

      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
        本文为只读内容，不可编辑。
      </Typography.Paragraph>

      <div style={{ textAlign: 'center', marginTop: 24 }}>
        <Space>
          <Button
            type="primary"
            disabled={finished}
            onClick={() => {
              if (bodyRef.current) {
                bodyRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
              }
              void onReachBottom()
            }}
          >
            {finished ? '本篇已读完' : '我已读完全文'}
          </Button>
          <Button
            onClick={async () => {
              try {
                const r = await articleApi.exportPdf(articleId)
                window.open(fileUrl(r.file_url), '_blank')
              } catch (e) {
                message.error(e instanceof Error ? e.message : '导出失败')
              }
            }}
          >
            导出 PDF
          </Button>
        </Space>
      </div>
    </Card>
  )
}