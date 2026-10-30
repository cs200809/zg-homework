/**
 * 学生端「我的」页（PRD 9.1、迭代 v2.1）。
 *
 * 展示绑定码（家长凭此绑定孩子）、所属班级，并提供修改密码入口。
 */
import { Button, Card, Descriptions, Space, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { post } from '../../api/client'
import { useAuthStore } from '../../store/auth'

interface ClassInfo {
  id: number
  name: string
  invite_code: string
}

export default function StudentProfile() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [klass, setKlass] = useState<ClassInfo | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const r = await post<{ role: string; classes: ClassInfo[] }>('/classes/my')
        setKlass(r.classes[0] ?? null)
      } catch {
        // 班级信息拉取失败不阻断本页展示
      }
    })()
  }, [])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="账号信息">
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="昵称">{user?.nickname || '-'}</Descriptions.Item>
          <Descriptions.Item label="身份">
            <Tag color="blue">学生</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="所属班级">
            {klass ? klass.name : '尚未加入班级'}
          </Descriptions.Item>
          <Descriptions.Item label="我的绑定码">
            <Typography.Text strong copyable={!!user?.bind_code}>
              {user?.bind_code || '未生成'}
            </Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
              家长注册时需要此绑定码，请告知家长。
            </Typography.Paragraph>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="安全">
        <Button onClick={() => navigate('/change-password')}>修改密码</Button>
      </Card>
    </Space>
  )
}
