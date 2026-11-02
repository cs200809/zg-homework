/// 我的页面（四角色通用，PRD 9）。
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/auth_state.dart';
import '../../widgets/common.dart';
import 'change_password_page.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final user = auth.user;

    return Scaffold(
      appBar: AppBar(title: const Text('我的')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const CircleAvatar(child: Icon(Icons.person)),
              title: Text(user?.nickname ?? user?.username ?? ''),
              subtitle: Text(
                '用户名：${user?.username ?? ''}\n角色：${_roleLabel(user?.role)}',
              ),
              isThreeLine: true,
            ),
          ),
          const SizedBox(height: 12),

          // 学生：显示绑定码供家长绑定（PRD 5.7）
          if (user?.role == 'student') ...[
            Card(
              color: Colors.blue.shade50,
              child: ListTile(
                leading: const Icon(Icons.qr_code),
                title: const Text('我的绑定码'),
                subtitle: Text(user!.bindCode ?? '未生成'),
                trailing: IconButton(
                  icon: const Icon(Icons.copy),
                  onPressed: () => showSnack(context, '请手动记录绑定码：${user.bindCode}'),
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],

          ListTile(
            leading: const Icon(Icons.lock_outline),
            title: const Text('修改密码'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ChangePasswordPage()),
            ),
          ),
          ListTile(
            leading: Icon(Icons.logout, color: Colors.red.shade600),
            title: Text('退出登录', style: TextStyle(color: Colors.red.shade600)),
            onTap: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (c) => AlertDialog(
                  title: const Text('确认退出登录？'),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(c, false),
                      child: const Text('取消'),
                    ),
                    FilledButton(
                      onPressed: () => Navigator.pop(c, true),
                      child: const Text('退出'),
                    ),
                  ],
                ),
              );
              if (ok == true && context.mounted) {
                await auth.logout();
              }
            },
          ),
        ],
      ),
    );
  }

  static String _roleLabel(String? role) => switch (role) {
    'admin' => '管理员',
    'teacher' => '老师',
    'student' => '学生',
    'parent' => '家长',
    _ => '未知',
  };
}