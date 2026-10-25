/** 主布局：侧边菜单按角色渲染（PRD 9）。 */

import { Layout, Menu, Dropdown, Avatar, Spin } from 'antd'
import {
  UserOutlined,
  LogoutOutlined,
  HomeOutlined,
  FileTextOutlined,
  BookOutlined,
  TrophyOutlined,
  PlayCircleOutlined,
  WalletOutlined,
  TeamOutlined,
  KeyOutlined,
  SettingOutlined,
  DashboardOutlined,
  SolutionOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation, Link } from 'react-router-dom'

import { ROLE_LABEL, useAuthStore } from '../store/auth'
import type { Role } from '../api/types'

const { Header, Sider, Content } = Layout

interface NavItem {
  key: string
  label: string
  icon: React.ReactNode
}

const MENUS: Record<Role, NavItem[]> = {
  student: [
    { key: '/student', label: '首页', icon: <HomeOutlined /> },
    { key: '/student/homework', label: '作业', icon: <FileTextOutlined /> },
    { key: '/student/reading', label: '阅读', icon: <BookOutlined /> },
    { key: '/student/games', label: '游戏', icon: <PlayCircleOutlined /> },
    { key: '/student/rank', label: '排行榜', icon: <TrophyOutlined /> },
    { key: '/student/points', label: '我的积分', icon: <WalletOutlined /> },
  ],
  teacher: [
    { key: '/teacher', label: '班级管理', icon: <TeamOutlined /> },
    { key: '/teacher/homework', label: '作业管理', icon: <FileTextOutlined /> },
    { key: '/teacher/articles', label: '文章管理', icon: <BookOutlined /> },
  ],
  admin: [
    { key: '/admin', label: '数据概览', icon: <DashboardOutlined /> },
    { key: '/admin/invites', label: '邀请码管理', icon: <KeyOutlined /> },
    { key: '/admin/users', label: '用户管理', icon: <UserOutlined /> },
    { key: '/admin/rules', label: '积分规则', icon: <SettingOutlined /> },
    { key: '/admin/articles', label: '文章管理', icon: <BookOutlined /> },
    { key: '/admin/classes', label: '班级总览', icon: <TeamOutlined /> },
    { key: '/admin/idioms', label: '成语题库', icon: <SolutionOutlined /> },
  ],
  parent: [
    { key: '/parent', label: '我的孩子', icon: <SolutionOutlined /> },
  ],
}

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, initialized, logout } = useAuthStore()

  if (!initialized || !user) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  const items = MENUS[user.role]
  // 高亮：取最长匹配的菜单项（避免 /teacher/homework/1 只命中 /teacher）
  const selected = items
    .map((i) => i.key)
    .filter((k) => location.pathname === k || location.pathname.startsWith(k + '/'))
    .sort((a, b) => b.length - a.length)[0]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div style={{ height: 32, margin: 16, color: '#fff', fontWeight: 600 }}>
          zg-tsp 平台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selected ? [selected] : []}
          items={items.map((i) => ({ key: i.key, icon: i.icon, label: <Link to={i.key}>{i.label}</Link> }))}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontWeight: 500 }}>{ROLE_LABEL[user.role]}端</span>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '退出登录',
                  onClick: () => {
                    logout()
                    navigate('/login')
                  },
                },
              ],
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{user.nickname || user.username}</span>
            </div>
          </Dropdown>
        </Header>

        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}