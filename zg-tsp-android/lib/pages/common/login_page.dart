/// 登录 / 注册 / 修改密码页（PRD 5.1、9 公共）。
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../state/auth_state.dart';
import '../../widgets/common.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final auth = context.read<AuthState>();
    try {
      await auth.login(_username.text.trim(), _password.text);
      if (!mounted) return;
      // admin 首登强制改密由根路由处理（must_change_password）
      Navigator.of(context).pushReplacementNamed('/home');
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final loading = context.watch<AuthState>().loading;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.school, size: 64, color: Colors.blue),
                  const SizedBox(height: 12),
                  Text(
                    'zg-tsp 学习平台',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _username,
                    decoration: const InputDecoration(
                      labelText: '用户名',
                      prefixIcon: Icon(Icons.person_outline),
                      border: OutlineInputBorder(),
                    ),
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? '请输入用户名' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _password,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: '密码',
                      prefixIcon: const Icon(Icons.lock_outline),
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscure ? Icons.visibility_off : Icons.visibility,
                        ),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    validator: (v) =>
                        (v == null || v.isEmpty) ? '请输入密码' : null,
                    onFieldSubmitted: (_) => _submit(),
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: loading ? null : _submit,
                    child: loading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('登录'),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () =>
                        Navigator.of(context).pushNamed('/register'),
                    child: const Text('没有账号？去注册'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _nickname = TextEditingController();
  final _inviteCode = TextEditingController();
  String _role = 'student';
  bool _submitting = false;

  static const _roles = [
    ('student', '学生'),
    ('parent', '家长'),
    ('teacher', '老师'),
  ];

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    _nickname.dispose();
    _inviteCode.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _submitting = true);
    try {
      await AuthApi.instance.register(
        username: _username.text.trim(),
        password: _password.text,
        role: _role,
        nickname: _nickname.text.trim(),
        teacherInviteCode: _inviteCode.text.trim(),
      );
      if (!mounted) return;
      showSnack(context, '注册成功，请登录');
      Navigator.of(context).pop();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('注册')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SegmentedButton<String>(
                  segments: _roles
                      .map((r) => ButtonSegment(value: r.$1, label: Text(r.$2)))
                      .toList(),
                  selected: {_role},
                  onSelectionChanged: (s) => setState(() => _role = s.first),
                ),
                const SizedBox(height: 20),
                TextFormField(
                  controller: _username,
                  decoration: const InputDecoration(
                    labelText: '用户名（3~20 位）',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) {
                    final s = v?.trim() ?? '';
                    if (s.isEmpty) return '请输入用户名';
                    if (s.length < 3 || s.length > 20) return '用户名 3~20 位';
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _password,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '密码（至少 6 位）',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) => (v == null || v.length < 6) ? '密码至少 6 位' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _nickname,
                  decoration: const InputDecoration(
                    labelText: '昵称（选填）',
                    border: OutlineInputBorder(),
                  ),
                ),
                // 老师必须填写邀请码（PRD 5.1）
                if (_role == 'teacher') ...[
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _inviteCode,
                    decoration: const InputDecoration(
                      labelText: '老师邀请码',
                      border: OutlineInputBorder(),
                    ),
                    validator: (v) => _role == 'teacher' && (v == null || v.isEmpty)
                        ? '老师注册必须填写邀请码'
                        : null,
                  ),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('注册'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class ChangePasswordPage extends StatefulWidget {
  const ChangePasswordPage({super.key, this.forced = false});

  /// true 时为 admin 首登强制改密（PRD 5.1）
  final bool forced;

  @override
  State<ChangePasswordPage> createState() => _ChangePasswordPageState();
}

class _ChangePasswordPageState extends State<ChangePasswordPage> {
  final _formKey = GlobalKey<FormState>();
  final _old = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _old.dispose();
    _new.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _submitting = true);
    try {
      await AuthApi.instance.changePassword(_old.text, _new.text);
      if (!mounted) return;
      await context.read<AuthState>().markPasswordChanged();
      if (!mounted) return;
      showSnack(context, '密码修改成功');
      if (widget.forced) {
        Navigator.of(context).pushReplacementNamed('/home');
      } else {
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.forced ? '首次登录，请修改密码' : '修改密码'),
        automaticallyImplyLeading: !widget.forced,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (widget.forced) ...[
                  Card(
                    color: Colors.orange.shade50,
                    child: const Padding(
                      padding: EdgeInsets.all(12),
                      child: Text('使用初始密码登录后必须修改密码，修改前无法使用其他功能。'),
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                TextFormField(
                  controller: _old,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '原密码',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) => (v == null || v.isEmpty) ? '请输入原密码' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _new,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '新密码（至少 6 位）',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) =>
                      (v == null || v.length < 6) ? '密码至少 6 位' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _confirm,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '确认新密码',
                    border: OutlineInputBorder(),
                  ),
                  validator: (v) =>
                      v != _new.text ? '两次输入的密码不一致' : null,
                ),
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _submitting ? null : _submit,
                  child: const Text('确认修改'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}