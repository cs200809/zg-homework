/// admin 端：概览 / 邀请码 / 用户 / 规则 / 文章（PRD 5.8、9 admin 端，移动精简版）。
library;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/config.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';
import '../common/profile_page.dart';
import 'idiom_bank_page.dart';

class AdminHome extends StatefulWidget {
  const AdminHome({super.key});

  @override
  State<AdminHome> createState() => _AdminHomeState();
}

class _AdminHomeState extends State<AdminHome> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: const [
          _OverviewPanel(),
          _InvitesPanel(),
          _UsersPanel(),
          _RulesPanel(),
          _AdminArticlesPanel(),
          IdiomBankPage(),
          ProfilePage(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: '概览',
          ),
          NavigationDestination(
            icon: Icon(Icons.key_outlined),
            selectedIcon: Icon(Icons.key),
            label: '邀请码',
          ),
          NavigationDestination(
            icon: Icon(Icons.people_outline),
            selectedIcon: Icon(Icons.people),
            label: '用户',
          ),
          NavigationDestination(
            icon: Icon(Icons.tune_outlined),
            selectedIcon: Icon(Icons.tune),
            label: '规则',
          ),
          NavigationDestination(
            icon: Icon(Icons.article_outlined),
            selectedIcon: Icon(Icons.article),
            label: '文章',
          ),
          NavigationDestination(
            icon: Icon(Icons.format_quote_outlined),
            selectedIcon: Icon(Icons.format_quote),
            label: '题库',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: '我的',
          ),
        ],
      ),
    );
  }
}

/// 文章管理（PRD 5.8.4、5.5、迭代 v2.1）
class _AdminArticlesPanel extends StatefulWidget {
  const _AdminArticlesPanel();

  @override
  State<_AdminArticlesPanel> createState() => _AdminArticlesPanelState();
}

class _AdminArticlesPanelState extends State<_AdminArticlesPanel> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await AdminApi.instance.articleList(page: 1, size: 50);
      if (!mounted) return;
      setState(() {
        _rows = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _create() async {
    final title = TextEditingController();
    final content = TextEditingController();
    String? filePath;

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setState) => AlertDialog(
          title: const Text('发布文章'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: title, decoration: const InputDecoration(labelText: '标题')),
              const SizedBox(height: 12),
              TextField(
                controller: content,
                maxLines: 6,
                decoration: const InputDecoration(
                  labelText: '正文',
                  helperText: '可留空，改为上传 PDF / Word',
                ),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () async {
                  final res = await FilePicker.platform.pickFiles(
                    type: FileType.custom,
                    allowedExtensions: const ['pdf', 'docx'],
                  );
                  final p = res?.files.single.path;
                  if (p != null) setState(() => filePath = p);
                },
                icon: const Icon(Icons.attach_file),
                label: Text(filePath == null ? '选择 PDF / Word（可选）' : '已选择文件'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('发布')),
          ],
        ),
      ),
    );
    if (ok == true && title.text.trim().isNotEmpty) {
      try {
        await AdminApi.instance.createArticle(
          title.text.trim(),
          content.text.trim(),
          filePath: filePath,
        );
        if (mounted) showSnack(context, '发布成功');
        await _load();
      } catch (e) {
        if (mounted) showSnack(context, errorMessage(e), error: true);
      }
    }
    title.dispose();
    content.dispose();
  }

  /// 导出 PDF（迭代 v2.1）
  Future<void> _exportPdf(int articleId) async {
    try {
      final r = await AdminApi.instance.exportPdf(articleId);
      final path = (r['file_url'] as String?) ?? '';
      if (path.isEmpty) throw Exception('未返回文件地址');
      final opened = await launchUrl(
        Uri.parse('${AppConfig.apiBaseUrl}$path'),
        mode: LaunchMode.externalApplication,
      );
      if (!opened && mounted) {
        showSnack(context, '无法打开 PDF，请检查网络或稍后重试', error: true);
      }
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('文章管理'),
        actions: [IconButton(icon: const Icon(Icons.add), onPressed: _create)],
      ),
      body: _loading
          ? const LoadingView()
          : _rows.isEmpty
          ? const EmptyView(message: '还没有发布文章')
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.all(12),
                itemCount: _rows.length,
                itemBuilder: (context, i) {
                  final a = _rows[i];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      title: Text(a['title'] as String? ?? ''),
                      subtitle: Text(
                        a['status'] == 'published' ? '已发布' : '已隐藏',
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            tooltip: '导出 PDF',
                            icon: const Icon(Icons.picture_as_pdf_outlined),
                            onPressed: () => _exportPdf(a['id'] as int),
                          ),
                          IconButton(
                            tooltip: '删除',
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () async {
                              final messenger = ScaffoldMessenger.of(context);
                              try {
                                await AdminApi.instance.deleteArticle(a['id'] as int);
                                if (!mounted) return;
                                messenger.showSnackBar(
                                  const SnackBar(content: Text('已删除')),
                                );
                                await _load();
                              } catch (e) {
                                if (!mounted) return;
                                messenger.showSnackBar(
                                  SnackBar(content: Text(errorMessage(e))),
                                );
                              }
                            },
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
    );
  }
}

/// 数据概览
class _OverviewPanel extends StatefulWidget {
  const _OverviewPanel();

  @override
  State<_OverviewPanel> createState() => _OverviewPanelState();
}

class _OverviewPanelState extends State<_OverviewPanel> {
  Json? _stats;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final stats = await AdminApi.instance.statsOverview();
      if (mounted) setState(() => _stats = stats);
    } catch (e) {
      setState(() => _error = errorMessage(e));
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _stats;
    return Scaffold(
      appBar: AppBar(
        title: const Text('数据概览'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
      ),
      body: _loading
          ? const LoadingView()
          : _error != null
          ? ErrorView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '用户总数',
                          value: '${s?['user_count'] ?? 0}',
                          suffix: '人',
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: StatCard(
                          label: '启用中',
                          value: '${s?['active_user_count'] ?? 0}',
                          suffix: '人',
                          color: Colors.green,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '老师',
                          value: '${s?['teacher_count'] ?? 0}',
                          suffix: '人',
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: StatCard(
                          label: '学生',
                          value: '${s?['student_count'] ?? 0}',
                          suffix: '人',
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '家长',
                          value: '${s?['parent_count'] ?? 0}',
                          suffix: '人',
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: StatCard(
                          label: '班级',
                          value: '${s?['class_count'] ?? 0}',
                          suffix: '个',
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '作业',
                          value: '${s?['homework_count'] ?? 0}',
                          suffix: '份',
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: StatCard(
                          label: '积分总量',
                          value: '${s?['point_total'] ?? 0}',
                          suffix: '分',
                          color: Colors.amber.shade700,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const _AdminClassesSection(),
                ],
              ),
            ),
    );
  }
}

/// 班级管理：查看邀请码 + 重新生成（PRD 5.2、迭代 v2.1）
class _AdminClassesSection extends StatefulWidget {
  const _AdminClassesSection();

  @override
  State<_AdminClassesSection> createState() => _AdminClassesSectionState();
}

class _AdminClassesSectionState extends State<_AdminClassesSection> {
  List<Map<String, dynamic>> _classes = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await AdminApi.instance.classes(page: 1, size: 50);
      if (!mounted) return;
      setState(() {
        _classes = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// 重新生成班级邀请码（迭代 v2.1）
  Future<void> _regenerateInvite(int classId) async {
    try {
      final r = await AdminApi.instance.regenerateClassInvite(classId);
      if (!mounted) return;
      showSnack(context, '新的邀请码：${r['invite_code']}');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const LoadingView();
    if (_classes.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text('暂无班级', style: TextStyle(color: Colors.grey)),
        ),
      );
    }
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('班级邀请码', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
          ..._classes.map(
            (c) => ListTile(
              dense: true,
              title: Text(c['name'] as String? ?? ''),
              subtitle: Text(
                '邀请码：${c['invite_code']} · 班主任：${c['teacher_name'] ?? '-'} · 学生 ${c['student_count'] ?? 0} 人',
              ),
              trailing: IconButton(
                tooltip: '重新生成邀请码',
                icon: const Icon(Icons.autorenew),
                onPressed: () => _regenerateInvite(c['id'] as int),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 邀请码管理
class _InvitesPanel extends StatefulWidget {
  const _InvitesPanel();

  @override
  State<_InvitesPanel> createState() => _InvitesPanelState();
}

class _InvitesPanelState extends State<_InvitesPanel> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;

  static const _status = {
    'unused': ('未使用', Colors.green),
    'used': ('已使用', Colors.grey),
    'expired': ('已过期', Colors.orange),
    'revoked': ('已撤销', Colors.red),
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await AdminApi.instance.inviteList();
      if (!mounted) return;
      setState(() {
        _rows = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _create() async {
    final count = TextEditingController(text: '5');
    var days = 7;

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setState) => AlertDialog(
          title: const Text('批量生成邀请码'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: count,
                decoration: const InputDecoration(labelText: '数量（1~50）'),
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                initialValue: days,
                decoration: const InputDecoration(labelText: '有效期（天）'),
                items: const [1, 7, 15, 30, 90]
                    .map((d) => DropdownMenuItem(value: d, child: Text('$d 天')))
                    .toList(),
                onChanged: (v) => setState(() => days = v ?? 7),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('生成')),
          ],
        ),
      ),
    );

    if (ok == true) {
      try {
        final n = int.tryParse(count.text.trim()) ?? 5;
        final r = await AdminApi.instance.createInvites(n, days);
        if (!mounted) return;
        final codes = ((r['codes'] as List?) ?? []).join('  ');
        showDialog(
          context: context,
          builder: (c) => AlertDialog(
            title: Text('已生成 ${r['count']} 个邀请码'),
            content: SelectableText(codes),
            actions: [
              FilledButton(onPressed: () => Navigator.pop(c), child: const Text('知道了')),
            ],
          ),
        );
        await _load();
      } catch (e) {
        if (mounted) showSnack(context, errorMessage(e), error: true);
      }
    }
    count.dispose();
  }

  Future<void> _revoke(int id) async {
    try {
      await AdminApi.instance.revokeInvite(id);
      if (mounted) showSnack(context, '已撤销');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('邀请码管理'),
        actions: [IconButton(icon: const Icon(Icons.add), onPressed: _create)],
      ),
      body: _loading
          ? const LoadingView()
          : _rows.isEmpty
          ? const EmptyView(message: '暂无邀请码，点击右上角生成')
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.all(12),
                itemCount: _rows.length,
                itemBuilder: (context, i) {
                  final r = _rows[i];
                  final st = _status[r['status']] ?? ('未知', Colors.grey);
                  return Card(
                    margin: const EdgeInsets.only(bottom: 6),
                    child: ListTile(
                      dense: true,
                      title: Text(r['code'] as String? ?? ''),
                      subtitle: Text(
                        r['expire_at'] == null
                            ? '不过期'
                            : '有效期至 ${_fmt(r['expire_at'] as String)}',
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Chip(
                            label: Text(st.$1, style: const TextStyle(fontSize: 11)),
                            backgroundColor: st.$2.withValues(alpha: .15),
                            side: BorderSide.none,
                          ),
                          if (r['status'] == 'unused') ...[
                            const SizedBox(width: 4),
                            IconButton(
                              icon: const Icon(Icons.block, size: 20),
                              color: Colors.red.shade600,
                              onPressed: () => _revoke(r['id'] as int),
                            ),
                          ],
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
    );
  }
}

/// 用户管理
class _UsersPanel extends StatefulWidget {
  const _UsersPanel();

  @override
  State<_UsersPanel> createState() => _UsersPanelState();
}

class _UsersPanelState extends State<_UsersPanel> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;
  String? _role;
  String? _status;

  static const _roleLabel = {
    'admin': '管理员',
    'teacher': '老师',
    'student': '学生',
    'parent': '家长',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final r = await AdminApi.instance.users(role: _role, status: _status);
      if (!mounted) return;
      setState(() {
        _rows = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggle(Map<String, dynamic> u) async {
    try {
      final active = u['status'] == 'active';
      if (active) {
        await AdminApi.instance.disableUser(u['id'] as int);
      } else {
        await AdminApi.instance.enableUser(u['id'] as int);
      }
      if (mounted) showSnack(context, active ? '已禁用' : '已启用');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  /// 重新生成学生绑定码（迭代 v2.1）
  Future<void> _regenerateBindCode(Map<String, dynamic> u) async {
    try {
      final r = await AdminApi.instance.regenerateBindCode(u['id'] as int);
      if (!mounted) return;
      showDialog(
        context: context,
        builder: (c) => AlertDialog(
          title: Text('${u['username']} 的新绑定码'),
          content: SelectableText(
            r['bind_code'] as String,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.bold,
              fontFamily: 'monospace',
            ),
          ),
          actions: [
            FilledButton(onPressed: () => Navigator.pop(c), child: const Text('知道了')),
          ],
        ),
      );
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  Future<void> _resetPassword(Map<String, dynamic> u) async {    try {
      final r = await AdminApi.instance.resetPassword(u['id'] as int);
      if (!mounted) return;
      showDialog(
        context: context,
        builder: (c) => AlertDialog(
          title: Text('重置 ${u['username']} 的密码'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('临时密码：'),
              SelectableText(
                r['temp_password'] as String,
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  fontFamily: 'monospace',
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                '用户下次登录将被强制改密',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
          ),
          actions: [
            FilledButton(onPressed: () => Navigator.pop(c), child: const Text('知道了')),
          ],
        ),
      );
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('用户管理')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String?>(
                    initialValue: _role,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: '角色', isDense: true),
                    items: [
                      const DropdownMenuItem(value: null, child: Text('全部')),
                      ..._roleLabel.entries.map(
                        (e) => DropdownMenuItem(value: e.key, child: Text(e.value)),
                      ),
                    ],
                    onChanged: (v) {
                      setState(() => _role = v);
                      _load();
                    },
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: DropdownButtonFormField<String?>(
                    initialValue: _status,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: '状态', isDense: true),
                    items: const [
                      DropdownMenuItem(value: null, child: Text('全部')),
                      DropdownMenuItem(value: 'active', child: Text('启用')),
                      DropdownMenuItem(value: 'disabled', child: Text('禁用')),
                    ],
                    onChanged: (v) {
                      setState(() => _status = v);
                      _load();
                    },
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const LoadingView()
                : _rows.isEmpty
                ? const EmptyView(message: '暂无用户')
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      itemCount: _rows.length,
                      itemBuilder: (context, i) {
                        final u = _rows[i];
                        final isAdmin = u['role'] == 'admin';
                        final active = u['status'] == 'active';
                        return Card(
                          margin: const EdgeInsets.only(bottom: 6),
                          child: ListTile(
                            dense: true,
                            leading: CircleAvatar(
                              child: Text('${u['username']}'.isEmpty
                                  ? '?'
                                  : '${u['username']}'.substring(0, 1).toUpperCase()),
                            ),
                            title: Text('${u['nickname'] ?? u['username']}'),
                            subtitle: Text(
                              '${_roleLabel[u['role']]} · ${active ? '启用' : '禁用'}'
                              '${u['role'] == 'student' ? ' · ${u['total_points']}分' : ''}',
                            ),
                            trailing: isAdmin
                                ? const Text(
                                    '不可操作',
                                    style: TextStyle(fontSize: 11, color: Colors.grey),
                                  )
                                : Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      TextButton(
                                        onPressed: () => _toggle(u),
                                        child: Text(active ? '禁用' : '启用'),
                                      ),
                                      TextButton(
                                        onPressed: () => _resetPassword(u),
                                        child: const Text('改密'),
                                      ),
                                      if (u['role'] == 'student')
                                        IconButton(
                                          tooltip: '重新生成绑定码',
                                          icon: const Icon(Icons.qr_code_2),
                                          onPressed: () => _regenerateBindCode(u),
                                        ),
                                    ],
                                  ),
                          ),
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

/// 积分规则
class _RulesPanel extends StatefulWidget {
  const _RulesPanel();

  @override
  State<_RulesPanel> createState() => _RulesPanelState();
}

class _RulesPanelState extends State<_RulesPanel> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await AdminApi.instance.rules();
      if (!mounted) return;
      setState(() {
        _rows = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggle(Map<String, dynamic> rule) async {
    try {
      await AdminApi.instance.updateRule(
        ruleKey: rule['rule_key'] as String,
        enabled: !(rule['enabled'] as bool),
      );
      if (mounted) {
        showSnack(context, rule['enabled'] == true ? '已禁用' : '已启用');
      }
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  Future<void> _edit(Map<String, dynamic> rule) async {
    final points = TextEditingController(text: '${rule['points']}');
    final limit = TextEditingController(
      text: rule['daily_limit'] == null ? '' : '${rule['daily_limit']}',
    );

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('${rule['rule_name']}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: points,
              decoration: const InputDecoration(labelText: '积分值'),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: limit,
              decoration: const InputDecoration(
                labelText: '日上限',
                helperText: '每天最多 N 次；留空表示不限',
              ),
              keyboardType: TextInputType.number,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('保存')),
        ],
      ),
    );

    if (ok == true) {
      try {
        await AdminApi.instance.updateRule(
          ruleKey: rule['rule_key'] as String,
          points: int.tryParse(points.text.trim()),
          dailyLimit: limit.text.trim().isEmpty
              ? null
              : int.tryParse(limit.text.trim()),
        );
        if (mounted) showSnack(context, '已更新，新的发放立即按新值执行');
        await _load();
      } catch (e) {
        if (mounted) showSnack(context, errorMessage(e), error: true);
      }
    }
    points.dispose();
    limit.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('积分规则'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)],
      ),
      body: _loading
          ? const LoadingView()
          : _rows.isEmpty
          ? const EmptyView(message: '暂无规则')
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.all(12),
                itemCount: _rows.length,
                itemBuilder: (context, i) {
                  final r = _rows[i];
                  final enabled = r['enabled'] as bool;
                  return Card(
                    margin: const EdgeInsets.only(bottom: 6),
                    child: ListTile(
                      title: Text(r['rule_name'] as String? ?? ''),
                      subtitle: Text(
                        '${r['rule_key']} · ${r['points']} 分'
                        '${r['daily_limit'] == null ? ' · 不限' : ' · 日${r['daily_limit']}次'}',
                        style: const TextStyle(fontSize: 11),
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Switch(
                            value: enabled,
                            onChanged: (_) => _toggle(r),
                          ),
                          IconButton(
                            icon: const Icon(Icons.edit, size: 20),
                            onPressed: () => _edit(r),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
    );
  }
}

String _fmt(String iso) {
  final dt = DateTime.tryParse(iso);
  if (dt == null) return iso;
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}';
}