/// zg-tsp-android 应用入口（P8）。
///
/// 登录后按角色分流到各自的底部导航（PRD 9）：
/// - student：首页 / 作业 / 阅读 / 游戏 / 我的
/// - parent  ：孩子 / 我的
/// - teacher ：班级 / 作业 / 文章 / 我的
/// - admin   ：概览 / 邀请码 / 用户 / 规则 / 我的
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/config.dart';
import 'pages/admin/admin_home.dart';
import 'pages/common/login_page.dart';
import 'pages/parent/parent_home.dart';
import 'pages/student/student_home.dart';
import 'pages/teacher/teacher_home.dart';
import 'state/auth_state.dart';

void main() {
  debugPrint(
    '[config] flavor=${AppConfig.flavor} api=${AppConfig.apiBaseUrl} '
    'isDev=${AppConfig.isDev}',
  );
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState()..init(),
      child: const ZgTspApp(),
    ),
  );
}

class ZgTspApp extends StatelessWidget {
  const ZgTspApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'zg-tsp',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1677FF)),
        useMaterial3: true,
      ),
      home: const RootGate(),
    );
  }
}

/// 根路由守卫：初始化完成前显示 loading；未登录进登录页；
/// admin 未改密强制进改密页（PRD 5.1）；已登录按角色分流。
class RootGate extends StatefulWidget {
  const RootGate({super.key});

  @override
  State<RootGate> createState() => _RootGateState();
}

class _RootGateState extends State<RootGate> {
  String? _lastUserKey;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();

    if (!auth.initialized) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!auth.isLoggedIn) {
      _lastUserKey = null;
      return const LoginPage();
    }
    if (auth.user!.mustChangePassword) {
      return const ChangePasswordPage(forced: true);
    }

    // 账号变化时重建，避免切换账号后沿用上一个角色的导航状态
    final key = '${auth.user!.id}:${auth.user!.role}';
    if (_lastUserKey != key) {
      _lastUserKey = key;
    }

    switch (auth.user!.role) {
      case 'student':
        return const StudentHome(key: ValueKey('student'));
      case 'parent':
        return const ParentHome(key: ValueKey('parent'));
      case 'teacher':
        return const TeacherHome(key: ValueKey('teacher'));
      case 'admin':
        return const AdminHome(key: ValueKey('admin'));
      default:
        return const LoginPage();
    }
  }
}