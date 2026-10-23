/** 路由与权限守卫（PRD 9）。 */

import { Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import type { ReactElement } from 'react'

import AdminLayout from '../components/AdminLayout'
import { ROLE_HOME, useAuthStore } from '../store/auth'
import type { Role } from '../api/types'

// 页面
import LoginPage from '../pages/common/Login'
import RegisterPage from '../pages/common/Register'
import ChangePasswordPage from '../pages/common/ChangePassword'
import NotFound from '../pages/common/NotFound'

import StudentHome from '../pages/student/Home'
import StudentHomework from '../pages/student/Homework'
import StudentHomeworkDetail from '../pages/student/HomeworkDetail'
import StudentReading from '../pages/student/Reading'
import StudentArticle from '../pages/student/Article'
import StudentGames from '../pages/student/Games'
import StudentRank from '../pages/student/Rank'
import StudentPoints from '../pages/student/Points'

import TeacherClasses from '../pages/teacher/Classes'
import TeacherHomework from '../pages/teacher/Homework'
import TeacherHomeworkRecords from '../pages/teacher/HomeworkRecords'
import TeacherArticles from '../pages/teacher/Articles'

import AdminDashboard from '../pages/admin/Dashboard'
import AdminInvites from '../pages/admin/Invites'
import AdminUsers from '../pages/admin/Users'
import AdminRules from '../pages/admin/Rules'
import AdminArticles from '../pages/admin/Articles'
import AdminClasses from '../pages/admin/Classes'

import ParentChildren from '../pages/parent/Children'
import ParentChildPoints from '../pages/parent/ChildPoints'

/** 未登录或角色不符时跳转。 */
function Protected({
  roles,
  children,
}: {
  roles: Role[]
  children: ReactElement
}): ReactElement {
  const { token, user, initialized } = useAuthStore()

  if (!initialized) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }
  if (!token || !user) return <Navigate to="/login" replace />
  // admin 首登未改密 → 强制进改密页（PRD 5.1）
  if (user.must_change_password) return <Navigate to="/change-password" replace />
  if (!roles.includes(user.role)) return <Navigate to={ROLE_HOME[user.role]} replace />

  return children
}

/** 已登录用户访问登录/注册页时跳回首页。 */
function GuestOnly({ children }: { children: ReactElement }): ReactElement {
  const { token, user, initialized } = useAuthStore()
  if (!initialized) return <>{children}</>
  if (token && user) return <Navigate to={ROLE_HOME[user.role]} replace />
  return children
}

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />

      <Route
        path="/login"
        element={
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        }
      />
      <Route
        path="/register"
        element={
          <GuestOnly>
            <RegisterPage />
          </GuestOnly>
        }
      />
      <Route path="/change-password" element={<ChangePasswordPage />} />

      {/* ---------- 学生端 ---------- */}
      <Route
        element={
          <Protected roles={['student']}>
            <AdminLayout />
          </Protected>
        }
      >
        <Route path="/student" element={<StudentHome />} />
        <Route path="/student/homework" element={<StudentHomework />} />
        <Route path="/student/homework/:id" element={<StudentHomeworkDetail />} />
        <Route path="/student/reading" element={<StudentReading />} />
        <Route path="/student/reading/:id" element={<StudentArticle />} />
        <Route path="/student/games" element={<StudentGames />} />
        <Route path="/student/rank" element={<StudentRank />} />
        <Route path="/student/points" element={<StudentPoints />} />
      </Route>

      {/* ---------- 老师端 ---------- */}
      <Route
        element={
          <Protected roles={['teacher']}>
            <AdminLayout />
          </Protected>
        }
      >
        <Route path="/teacher" element={<TeacherClasses />} />
        <Route path="/teacher/homework" element={<TeacherHomework />} />
        <Route path="/teacher/homework/:id" element={<TeacherHomeworkRecords />} />
        <Route path="/teacher/articles" element={<TeacherArticles />} />
      </Route>

      {/* ---------- admin 端 ---------- */}
      <Route
        element={
          <Protected roles={['admin']}>
            <AdminLayout />
          </Protected>
        }
      >
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/invites" element={<AdminInvites />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/rules" element={<AdminRules />} />
        <Route path="/admin/articles" element={<AdminArticles />} />
        <Route path="/admin/classes" element={<AdminClasses />} />
      </Route>

      {/* ---------- 家长端 ---------- */}
      <Route
        element={
          <Protected roles={['parent']}>
            <AdminLayout />
          </Protected>
        }
      >
        <Route path="/parent" element={<ParentChildren />} />
        <Route path="/parent/children/:id" element={<ParentChildPoints />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}