/// 老师端：班级 / 作业 / 文章（PRD 5.2、5.3、5.5、9 老师端，移动精简版）。
library;

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';
import '../common/profile_page.dart';

class TeacherHome extends StatefulWidget {
  const TeacherHome({super.key});

  @override
  State<TeacherHome> createState() => _TeacherHomeState();
}

class _TeacherHomeState extends State<TeacherHome> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    const pages = [
      _ClassesPanel(),
      _HomeworkPanel(),
      _ArticlesPanel(),
      ProfilePage(),
    ];

    return Scaffold(
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.groups_outlined),
            selectedIcon: Icon(Icons.groups),
            label: '班级',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: '作业',
          ),
          NavigationDestination(
            icon: Icon(Icons.book_outlined),
            selectedIcon: Icon(Icons.book),
            label: '文章',
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

/// 班级面板
class _ClassesPanel extends StatefulWidget {
  const _ClassesPanel();

  @override
  State<_ClassesPanel> createState() => _ClassesPanelState();
}

class _ClassesPanelState extends State<_ClassesPanel> {
  List<Map<String, dynamic>> _classes = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await TeacherApi.instance.myClasses();
      if (!mounted) return;
      setState(() {
        _classes = ((r['classes'] as List?) ?? [])
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
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('创建班级'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(labelText: '班级名称'),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(c, controller.text.trim()),
            child: const Text('创建'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (name == null || name.isEmpty) return;

    try {
      final r = await TeacherApi.instance.createClass(name);
      if (!mounted) return;
      showSnack(context, '创建成功，邀请码：${r['class']['invite_code']}');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的班级'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
          IconButton(icon: const Icon(Icons.add), onPressed: _create),
        ],
      ),
      body: _loading
          ? const LoadingView()
          : _classes.isEmpty
          ? const EmptyView(message: '还没有班级，点击右上角 + 创建')
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.all(12),
                itemCount: _classes.length,
                itemBuilder: (context, i) {
                  final c = _classes[i];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      title: Text(c['name'] as String? ?? ''),
                      subtitle: Text(
                        '邀请码：${c['invite_code']} · 学生 ${c['student_count'] ?? 0} 人',
                      ),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => _ClassStudentsPage(
                              classId: c['id'] as int,
                              name: c['name'] as String,
                            ),
                          ),
                        );
                        _load();
                      },
                    ),
                  );
                },
              ),
            ),
    );
  }
}

class _ClassStudentsPage extends StatefulWidget {
  const _ClassStudentsPage({required this.classId, required this.name});

  final int classId;
  final String name;

  @override
  State<_ClassStudentsPage> createState() => _ClassStudentsPageState();
}

class _ClassStudentsPageState extends State<_ClassStudentsPage> {
  List<Map<String, dynamic>> _students = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await TeacherApi.instance.classStudents(widget.classId);
      if (!mounted) return;
      setState(() {
        _students = ((r['students'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _remove(int studentId) async {
    try {
      await TeacherApi.instance.removeStudent(widget.classId, studentId);
      if (!mounted) return;
      showSnack(context, '已移出');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('${widget.name} · 学生')),
      body: _loading
          ? const LoadingView()
          : _students.isEmpty
          ? const EmptyView(message: '暂无学生')
          : ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _students.length,
              itemBuilder: (context, i) {
                final s = _students[i];
                return Card(
                  margin: const EdgeInsets.only(bottom: 6),
                  child: ListTile(
                    dense: true,
                    leading: const CircleAvatar(child: Icon(Icons.person)),
                    title: Text(s['nickname'] as String? ?? s['username'] as String? ?? ''),
                    subtitle: Text('用户名：${s['username']}'),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Chip(label: Text('${s['total_points']} 分')),
                        IconButton(
                          icon: Icon(Icons.person_remove, color: Colors.red.shade600),
                          onPressed: () => _remove(s['id'] as int),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}

/// 作业面板
class _HomeworkPanel extends StatefulWidget {
  const _HomeworkPanel();

  @override
  State<_HomeworkPanel> createState() => _HomeworkPanelState();
}

class _HomeworkPanelState extends State<_HomeworkPanel> {
  List<Map<String, dynamic>> _classes = [];
  List<Map<String, dynamic>> _rows = [];
  int? _classId;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      final r = await TeacherApi.instance.myClasses();
      final classes = ((r['classes'] as List?) ?? [])
          .map((e) => e as Map<String, dynamic>)
          .toList();
      if (!mounted) return;
      setState(() {
        _classes = classes;
        if (classes.isNotEmpty) _classId = classes.first['id'] as int;
      });
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _load() async {
    if (_classId == null) return;
    setState(() => _loading = true);
    try {
      final r = await TeacherApi.instance.homeworkList(_classId!);
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
    if (_classId == null) return;
    final title = TextEditingController();
    final desc = TextEditingController();
    String subject = '语文';
    var deadline = DateTime.now().add(const Duration(days: 1));

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setState) => AlertDialog(
          title: const Text('布置作业'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: title,
                  decoration: const InputDecoration(labelText: '标题'),
                  autofocus: true,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: subject,
                  decoration: const InputDecoration(labelText: '科目'),
                  items: ['语文', '数学', '英语', '科学', '道法']
                      .map((s) => DropdownMenuItem(value: s, child: Text(s)))
                      .toList(),
                  onChanged: (v) => setState(() => subject = v ?? '语文'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: desc,
                  maxLines: 3,
                  decoration: const InputDecoration(labelText: '作业要求（选填）'),
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('截止时间'),
                  subtitle: Text(deadline.toString().substring(0, 16)),
                  trailing: const Icon(Icons.schedule),
                  onTap: () async {
                    final d = await showDatePicker(
                      context: c,
                      initialDate: deadline,
                      firstDate: DateTime.now(),
                      lastDate: DateTime.now().add(const Duration(days: 90)),
                    );
                    if (d != null) setState(() => deadline = d);
                  },
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('布置')),
          ],
        ),
      ),
    );

    if (ok == true && title.text.trim().isNotEmpty) {
      String two(int v) => v.toString().padLeft(2, '0');
      try {
        await TeacherApi.instance.createHomework(
          classId: _classId!,
          title: title.text.trim(),
          description: desc.text.trim(),
          subject: subject,
          deadline:
              '${deadline.year}-${two(deadline.month)}-${two(deadline.day)}T${two(deadline.hour)}:${two(deadline.minute)}:00',
        );
        if (mounted) showSnack(context, '布置成功');
        await _load();
      } catch (e) {
        if (mounted) showSnack(context, errorMessage(e), error: true);
      }
    }
    title.dispose();
    desc.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('作业管理'),
        actions: [IconButton(icon: const Icon(Icons.add), onPressed: _create)],
      ),
      body: Column(
        children: [
          if (_classes.isNotEmpty)
            Padding(
              padding: const EdgeInsets.all(8),
              child: DropdownButtonFormField<int>(
                initialValue: _classId,
                decoration: const InputDecoration(labelText: '选择班级', isDense: true),
                items: _classes
                    .map((c) => DropdownMenuItem(value: c['id'] as int, child: Text(c['name'] as String)))
                    .toList(),
                onChanged: (v) {
                  setState(() => _classId = v);
                  _load();
                },
              ),
            ),
          Expanded(
            child: _loading
                ? const LoadingView()
                : _rows.isEmpty
                ? const EmptyView(message: '还没有作业，点击右上角 + 布置')
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: _rows.length,
                      itemBuilder: (context, i) {
                        final hw = _rows[i];
                        return Card(
                          margin: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            title: Text(hw['title'] as String? ?? ''),
                            subtitle: Text('截止 ${_fmt(hw['deadline'] as String)}'),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () async {
                              await Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) =>
                                      _HomeworkRecordsPage(homeworkId: hw['id'] as int),
                                ),
                              );
                              _load();
                            },
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

/// 完成情况
class _HomeworkRecordsPage extends StatefulWidget {
  const _HomeworkRecordsPage({required this.homeworkId});

  final int homeworkId;

  @override
  State<_HomeworkRecordsPage> createState() => _HomeworkRecordsPageState();
}

class _HomeworkRecordsPageState extends State<_HomeworkRecordsPage> {
  Json? _data;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await TeacherApi.instance.homeworkRecords(widget.homeworkId);
      if (mounted) setState(() => _data = r);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: LoadingView());
    final rows = (_data?['records'] as List?) ?? [];
    final total = (_data?['total_students'] as int?) ?? 0;
    final submitted = (_data?['submitted_count'] as int?) ?? 0;

    return Scaffold(
      appBar: AppBar(title: Text(_data?['homework']?['title'] as String? ?? '完成情况')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: StatCard(
                    label: '提交率',
                    value: total > 0 ? '${(submitted / total * 100).round()}' : '0',
                    suffix: '%',
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(child: StatCard(label: '已提交', value: '$submitted', suffix: '/ $total')),
              ],
            ),
          ),
          Expanded(
            child: rows.isEmpty
                ? const EmptyView(message: '本班暂无学生')
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    itemCount: rows.length,
                    itemBuilder: (context, i) {
                      final r = rows[i] as Map<String, dynamic>;
                      final status = r['status'] as String? ?? 'not_started';
                      return Card(
                        margin: const EdgeInsets.only(bottom: 6),
                        child: ListTile(
                          dense: true,
                          title: Text(r['nickname'] as String? ?? r['username'] as String? ?? ''),
                          subtitle: Text(
                            r['start_time'] == null
                                ? '未开始'
                                : '用时 ${r['duration_minutes'] ?? '-'} 分钟'
                                      '${r['suspicious'] == true ? ' ⚠待审核' : ''}',
                          ),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Chip(
                                label: Text(homeworkStatusLabel[status] ?? status,
                                    style: const TextStyle(fontSize: 11)),
                                backgroundColor:
                                    (homeworkStatusColor[status] ?? Colors.grey)
                                        .withValues(alpha: .15),
                                side: BorderSide.none,
                              ),
                              const SizedBox(width: 4),
                              Text('${r['points'] ?? 0}分'),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

/// 文章面板
class _ArticlesPanel extends StatefulWidget {
  const _ArticlesPanel();

  @override
  State<_ArticlesPanel> createState() => _ArticlesPanelState();
}

class _ArticlesPanelState extends State<_ArticlesPanel> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await TeacherApi.instance.articleList();
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
    final title = TextEditingController();
    final content = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('发布文章'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: title, decoration: const InputDecoration(labelText: '标题')),
            const SizedBox(height: 12),
            TextField(
              controller: content,
              maxLines: 6,
              decoration: const InputDecoration(labelText: '正文'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('发布')),
        ],
      ),
    );
    if (ok == true && title.text.trim().isNotEmpty) {
      try {
        await TeacherApi.instance.createArticle(title.text.trim(), content.text.trim());
        if (mounted) showSnack(context, '发布成功');
        await _load();
      } catch (e) {
        if (mounted) showSnack(context, errorMessage(e), error: true);
      }
    }
    title.dispose();
    content.dispose();
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
                      trailing: IconButton(
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () async {
                          final messenger = ScaffoldMessenger.of(context);
                          try {
                            await TeacherApi.instance.deleteArticle(a['id'] as int);
                            if (!mounted) return;
                            messenger
                              ..hideCurrentSnackBar()
                              ..showSnackBar(const SnackBar(content: Text('已删除')));
                            _load();
                          } catch (e) {
                            if (!mounted) return;
                            messenger
                              ..hideCurrentSnackBar()
                              ..showSnackBar(SnackBar(content: Text(errorMessage(e))));
                          }
                        },
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
  return '${dt.year}-${two(dt.month)}-${two(dt.day)} ${two(dt.hour)}:${two(dt.minute)}';
}