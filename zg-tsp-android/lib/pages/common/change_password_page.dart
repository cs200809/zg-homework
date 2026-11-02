/// 修改密码页（PRD 5.1、9 公共）。
///
/// 从 login_page.dart 拆出：登录页文件不应承载改密页。
/// - forced=true：admin 首登强制改密，RootGate 直接把它作为 home 内容；
///   改密成功后由 AuthState.markPasswordChanged() 通知 RootGate 自动分流，本页不跳转。
/// - forced=false：从「我的」页进入，改密成功后 pop 回来源页。
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../state/auth_state.dart';
import '../../widgets/common.dart';

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
        // 强制改密场景下本页就是 RootGate 的 home 内容，markPasswordChanged()
        // 已 notifyListeners，RootGate 会自动切到对应角色的首页，无需跳转。
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
