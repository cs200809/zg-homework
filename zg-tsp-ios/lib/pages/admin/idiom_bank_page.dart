/// admin 端：成语题库管理（PRD 5.8.6，移动精简版）。
///
/// - 批量导入（粘贴 JSON，单次上限 1000 条）
/// - 列表：关键词 + 启用状态筛选、分页
/// - 单条编辑 / 删除；批量删除
/// - 禁用后学生端不再抽到
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../widgets/common.dart';

class IdiomBankPage extends StatefulWidget {
  const IdiomBankPage({super.key});

  @override
  State<IdiomBankPage> createState() => _IdiomBankPageState();
}

class _IdiomBankPageState extends State<IdiomBankPage> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;
  int _page = 1;
  int _total = 0;
  String _keyword = '';
  bool? _enabled;
  final Set<int> _selected = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final r = await AdminApi.instance.idiomList(
        page: _page,
        size: 20,
        keyword: _keyword.isEmpty ? null : _keyword,
        enabled: _enabled,
      );
      if (!mounted) return;
      setState(() {
        _rows = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
        _total = (r['total'] as int?) ?? 0;
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _import() async {
    final controller = TextEditingController();
    var mode = 'skip';

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, setState) => AlertDialog(
          title: const Text('批量导入'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: mode,
                decoration: const InputDecoration(labelText: '已存在的题目'),
                items: const [
                  DropdownMenuItem(value: 'skip', child: Text('跳过（skip）')),
                  DropdownMenuItem(value: 'overwrite', child: Text('覆盖（overwrite）')),
                ],
                onChanged: (v) => setState(() => mode = v ?? 'skip'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                maxLines: 6,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                decoration: const InputDecoration(
                  labelText: 'JSON 数组',
                  hintText: '[{"prompt":"画蛇添足","answer":"画蛇添足"}]',
                  alignLabelWithHint: true,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('取消')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('导入')),
          ],
        ),
      ),
    );

    if (ok != true || !mounted) {
      controller.dispose();
      return;
    }

    try {
      final parsed = jsonDecode(controller.text);
      final arr = parsed is List ? parsed : (parsed as Map)['items'];
      if (arr is! List || arr.isEmpty) {
        if (mounted) showSnack(context, 'JSON 格式错误或为空', error: true);
        controller.dispose();
        return;
      }
      if (arr.length > 1000) {
        if (mounted) showSnack(context, '单次最多导入 1000 条', error: true);
        controller.dispose();
        return;
      }

      final items = arr
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList();
      final r = await AdminApi.instance.importIdioms(items, mode);
      if (!mounted) return;
      showSnack(
        context,
        '导入完成：新增 ${r['success_count']}、更新 ${r['updated_count']}、'
        '跳过 ${r['skipped_count']}',
      );
      setState(() => _page = 1);
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      controller.dispose();
    }
  }

  Future<void> _toggle(Map<String, dynamic> q) async {
    try {
      await AdminApi.instance.updateIdiom(
        questionId: q['id'] as int,
        enabled: !(q['enabled'] as bool),
      );
      if (mounted) {
        showSnack(context, q['enabled'] == true ? '已禁用' : '已启用');
      }
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  Future<void> _edit(Map<String, dynamic> q) async {
    final prompt = TextEditingController(text: q['prompt'] as String? ?? '');
    final answer = TextEditingController(text: q['answer'] as String? ?? '');
    final distractors = TextEditingController(
      text: ((q['distractors'] as List?) ?? []).join('、'),
    );

    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('编辑题目'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: prompt, decoration: const InputDecoration(labelText: '题干')),
            const SizedBox(height: 12),
            TextField(controller: answer, decoration: const InputDecoration(labelText: '答案')),
            const SizedBox(height: 12),
            TextField(
              controller: distractors,
              decoration: const InputDecoration(
                labelText: '干扰项',
                helperText: '用顿号或逗号分隔',
              ),
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
        await AdminApi.instance.updateIdiom(
          questionId: q['id'] as int,
          prompt: prompt.text.trim(),
          answer: answer.text.trim(),
          distractors: distractors.text
              .split(RegExp(r'[,，、\s]+'))
              .where((e) => e.isNotEmpty)
              .toList(),
        );
        if (mounted) showSnack(context, '已保存');
        await _load();
      } catch (e) {
        if (mounted) showSnack(context, errorMessage(e), error: true);
      }
    }
    prompt.dispose();
    answer.dispose();
    distractors.dispose();
  }

  Future<void> _delete(int id) async {
    try {
      await AdminApi.instance.deleteIdiom(id);
      if (mounted) showSnack(context, '已删除');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  Future<void> _batchDelete() async {
    if (_selected.isEmpty) return;
    try {
      final r = await AdminApi.instance.batchDeleteIdioms(_selected.toList());
      if (mounted) {
        showSnack(context, '已删除 ${r['deleted_count']} 条');
        setState(() => _selected.clear());
      }
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('成语题库'),
        actions: [IconButton(icon: const Icon(Icons.add), onPressed: _import)],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    decoration: const InputDecoration(
                      labelText: '搜索',
                      isDense: true,
                      prefixIcon: Icon(Icons.search),
                    ),
                    onSubmitted: (v) {
                      setState(() {
                        _page = 1;
                        _keyword = v.trim();
                      });
                      _load();
                    },
                  ),
                ),
                const SizedBox(width: 8),
                DropdownButton<bool?>(
                  value: _enabled,
                  hint: const Text('状态'),
                  items: const [
                    DropdownMenuItem(value: null, child: Text('全部')),
                    DropdownMenuItem(value: true, child: Text('启用')),
                    DropdownMenuItem(value: false, child: Text('禁用')),
                  ],
                  onChanged: (v) {
                    setState(() {
                      _page = 1;
                      _enabled = v;
                    });
                    _load();
                  },
                ),
              ],
            ),
          ),
          if (_selected.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Row(
                children: [
                  Text('已选 ${_selected.length} 条'),
                  const Spacer(),
                  TextButton(
                    onPressed: _batchDelete,
                    child: const Text('批量删除', style: TextStyle(color: Colors.red)),
                  ),
                ],
              ),
            ),
          Expanded(
            child: _loading
                ? const LoadingView()
                : _rows.isEmpty
                ? const EmptyView(message: '题库为空，点击右上角 + 导入')
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: _rows.length,
                      itemBuilder: (context, i) {
                        final q = _rows[i];
                        final id = q['id'] as int;
                        return Card(
                          margin: const EdgeInsets.only(bottom: 6),
                          child: CheckboxListTile(
                            value: _selected.contains(id),
                            onChanged: (v) => setState(() {
                              if (v == true) {
                                _selected.add(id);
                              } else {
                                _selected.remove(id);
                              }
                            }),
                            title: Text(q['prompt'] as String? ?? ''),
                            subtitle: Text(
                              '答案：${q['answer']}'
                              '${((q['distractors'] as List?) ?? []).isEmpty ? '' : ' · 干扰 ${((q['distractors'] as List?) ?? []).join('、')}'}',
                              style: const TextStyle(fontSize: 11),
                            ),
                            secondary: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Switch(
                                  value: q['enabled'] as bool,
                                  onChanged: (_) => _toggle(q),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.edit, size: 18),
                                  onPressed: () => _edit(q),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline, size: 18),
                                  color: Colors.red.shade600,
                                  onPressed: () => _delete(id),
                                ),
                              ],
                            ),
                            controlAffinity: ListTileControlAffinity.leading,
                            isThreeLine: false,
                          ),
                        );
                      },
                    ),
                  ),
          ),
          if (_total > 20)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Text('第 $_page 页 / 共 $_total 条'),
                  IconButton(
                    icon: const Icon(Icons.chevron_right),
                    onPressed: () {
                      setState(() => _page++);
                      _load();
                    },
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
