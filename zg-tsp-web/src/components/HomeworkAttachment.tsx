import { useState } from 'react'
import { App, Button } from 'antd'

import { client, downloadErrorMessage, fileUrl } from '../api/client'

interface Props {
  url: string
  studentId: number
  homeworkId: number
  children: string
}

/** 新附件需鉴权下载；历史公开附件仍直接打开。 */
export default function HomeworkAttachment({ url, studentId, homeworkId, children }: Props) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)

  if (url !== '/homework/attachment') {
    return <a href={fileUrl(url)} target="_blank" rel="noreferrer">{children}</a>
  }

  async function download() {
    setLoading(true)
    try {
      const response = await client.post<Blob>(
        '/homework/attachment',
        { student_id: studentId, homework_id: homeworkId },
        { responseType: 'blob' },
      )
      if (response.data.type.includes('application/json')) {
        const payload = JSON.parse(await response.data.text()) as { message?: string }
        throw new Error(payload.message || '下载附件失败')
      }
      const objectUrl = URL.createObjectURL(response.data)
      try {
        const disposition = response.headers['content-disposition'] as string | undefined
        const encoded = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
        const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1]
        const link = document.createElement('a')
        link.href = objectUrl
        try { link.download = encoded ? decodeURIComponent(encoded) : filename || '作业附件' }
        catch { link.download = filename || '作业附件' }
        link.click()
      } finally {
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      }
    } catch (error) {
      message.error(await downloadErrorMessage(error, '下载附件失败'))
    } finally {
      setLoading(false)
    }
  }

  return <Button type="link" style={{ padding: 0 }} loading={loading} onClick={download}>{children}</Button>
}
