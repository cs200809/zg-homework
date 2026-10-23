/// 家长端：孩子列表 + 积分明细 + 积分消耗（PRD 5.7、9 家长端）。
library;

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';
import '../common/profile_page.dart';

class ParentHome extends StatefulWidget {
  const ParentHome({super.key});

  @override
  State<ParentHome> createState() => _ParentHomeState();
}

class _ParentHomeState extends State<ParentHome> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: const [_ChildrenPanel(), ProfilePage()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.child_care_outlined),
            selectedIcon: Icon(Icons.child_care),
            label: '我的孩子',
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

class _ChildrenPanel extends StatefulWidget {
  const _ChildrenPanel();

  @override
  State<_ChildrenPanel> createState() => _ChildrenPanelState();
}

class _ChildrenPanelState extends State<_ChildrenPanel> {
  List<Map<String, dynamic>> _children = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await ParentApi.instance.children();
      if (!mounted) return;
      setState(() {
        _children = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _bind() async {
    final controller = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('绑定孩子'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: '孩子绑定码',
            hintText: '让孩子在「我的」页面查看',
          ),
          maxLength: 8,
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: const Text('取消')),
          FilledButton(
            onPressed: () => Navigator.pop(c, controller.text.trim()),
            child: const Text('绑定'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (code == null || code.isEmpty) return;

    try {
      final r = await ParentApi.instance.bind(code);
      if (!mounted) return;
      showSnack(context, '已绑定 ${r['nickname'] ?? r['username']}');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的孩子'),
        actions: [IconButton(icon: const Icon(Icons.person_add), onPressed: _bind)],
      ),
      body: _loading
          ? const LoadingView()
          : _children.isEmpty
          ? const EmptyView(message: '还没有绑定孩子，点击右上角绑定')
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.all(12),
                itemCount: _children.length,
                itemBuilder: (context, i) {
                  final c = _children[i];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      leading: const CircleAvatar(child: Icon(Icons.child_care)),
                      title: Text(c['nickname'] as String? ?? c['username'] as String? ?? ''),
                      subtitle: Text('用户名：${c['username']}'),
                      trailing: Chip(
                        label: Text('${c['total_points']} 分'),
                        backgroundColor: Colors.amber.withValues(alpha: .15),
                        side: BorderSide.none,
                      ),
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => ChildPointsPage(
                              studentId: c['student_id'] as int,
                              name: c['nickname'] as String? ?? c['username'] as String? ?? '孩子',
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

/// 孩子积分明细 + 消耗
class ChildPointsPage extends StatefulWidget {
  const ChildPointsPage({super.key, required this.studentId, required this.name});

  final int studentId;
  final String name;

  @override
  State<ChildPointsPage> createState() => _ChildPointsPageState();
}

class _ChildPointsPageState extends State<ChildPointsPage> {
  Json? _summary;
  List<Map<String, dynamic>> _rows = [];
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        ParentApi.instance.childPoints(widget.studentId),
        ParentApi.instance.consumeItems(),
      ]);
      if (!mounted) return;
      setState(() {
        _summary = results[0]['summary'];
        _rows = ((results[0]['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
        _items = ((results[1]['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _consume(String item, int points) async {
    try {
      final r = await ParentApi.instance.consume(widget.studentId, item, points);
      if (!mounted) return;
      showSnack(context, '已扣减 ${r['points']} 分，剩余 ${r['total_points']} 分');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final balance = (_summary?['total_points'] as int?) ?? 0;

    return Scaffold(
      appBar: AppBar(title: Text('${widget.name} 的积分')),
      body: _loading
          ? const LoadingView()
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '当前余额',
                          value: '$balance',
                          suffix: '分',
                          color: Colors.amber.shade700,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: StatCard(
                          label: '累计获得',
                          value: '${_summary?['total_gained'] ?? 0}',
                          suffix: '分',
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: StatCard(
                          label: '累计消费',
                          value: '${_summary?['total_consumed'] ?? 0}',
                          suffix: '分',
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Text('快速消耗', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final it in _items)
                        ActionChip(
                          label: Text('${it['name']} -${it['points']}'),
                          onPressed: () => _consume(it['name'] as String, it['points'] as int),
                          backgroundColor: Colors.red.withValues(alpha: .08),
                        ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: () => _showCustomConsume(),
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('自定义扣分'),
                  ),
                  const SizedBox(height: 16),
                  Text('积分明细', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  if (_rows.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: EmptyView(message: '暂无积分记录'),
                    )
                  else
                    for (final r in _rows)
                      Card(
                        margin: const EdgeInsets.only(bottom: 6),
                        child: ListTile(
                          dense: true,
                          leading: Chip(
                            label: Text(pointTypeLabel[r['type']] ?? '${r['type']}'),
                            backgroundColor:
                                (pointTypeColor[r['type']] ?? Colors.grey).withValues(alpha: .15),
                            side: BorderSide.none,
                          ),
                          title: Text(r['remark'] as String? ?? '-'),
                          subtitle: Text('${r['log_date'] ?? ''}'),
                          trailing: Text(
                            '${(r['points'] as int) > 0 ? '+' : ''}${r['points']}',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: (r['points'] as int) >= 0 ? Colors.green : Colors.red,
                            ),
                          ),
                        ),
                      ),
                ],
              ),
            ),
    );
  }

  Future<void> _showCustomConsume() async {
    final item = TextEditingController();
    final points = TextEditingController();

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('自定义扣分'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: item,
              decoration: const InputDecoration(labelText: '事项'),
              autofocus: true,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: points,
              decoration: const InputDecoration(labelText: '扣减分数'),
              keyboardType: TextInputType.number,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
          FilledButton(
            onPressed: () {
              final p = int.tryParse(points.text.trim());
              if (p == null || p <= 0) return;
              Navigator.pop(c, true);
            },
            child: const Text('确认'),
          ),
        ],
      ),
    );

    if (ok == true && item.text.trim().isNotEmpty) {
      await _consume(item.text.trim(), int.parse(points.text.trim()));
    }
    item.dispose();
    points.dispose();
  }
}