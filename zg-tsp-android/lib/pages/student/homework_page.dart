/// 学生端：作业列表与详情（PRD 5.3）。
library;

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';

class HomeworkPage extends StatefulWidget {
  const HomeworkPage({super.key});

  @override
  State<HomeworkPage> createState() => _HomeworkPageState();
}

class _HomeworkPageState extends State<HomeworkPage> {
  Json? _data;
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
      final data = await StudentApi.instance.todayHomework();
      if (mounted) setState(() => _data = data);
    } catch (e) {
      setState(() => _error = errorMessage(e));
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('今日作业')),
      body: _loading
          ? const LoadingView()
          : _error != null
          ? ErrorView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: _buildList(),
            ),
    );
  }

  Widget _buildList() {
    final list = (_data?['list'] as List?) ?? [];
    if (list.isEmpty) {
      return LayoutBuilder(
        builder: (context, c) => SizedBox(
          height: c.maxHeight,
          child: const EmptyView(message: '今天没有作业'),
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final hw = list[i] as Map<String, dynamic>;
        final status = hw['my_status'] as String? ?? 'not_started';
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            title: Text(hw['title'] as String? ?? ''),
            subtitle: Text(
              '截止 ${_fmt(hw['deadline'] as String)}'
              '${hw['subject'] == null ? '' : ' · ${hw['subject']}'}',
            ),
            trailing: Chip(
              label: Text(
                homeworkStatusLabel[status] ?? status,
                style: const TextStyle(fontSize: 11),
              ),
              visualDensity: VisualDensity.compact,
              backgroundColor:
                  (homeworkStatusColor[status] ?? Colors.grey).withValues(alpha: .12),
              side: BorderSide.none,
            ),
            onTap: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => HomeworkDetailPage(homeworkId: hw['id'] as int),
                ),
              );
              _load();
            },
          ),
        );
      },
    );
  }
}

/// 作业详情：开始计时 → 作答 → 提交
class HomeworkDetailPage extends StatefulWidget {
  const HomeworkDetailPage({super.key, required this.homeworkId});

  final int homeworkId;

  @override
  State<HomeworkDetailPage> createState() => _HomeworkDetailPageState();
}

class _HomeworkDetailPageState extends State<HomeworkDetailPage> {
  Json? _data;
  bool _loading = true;
  bool _submitting = false;
  final _text = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final d = await StudentApi.instance.homeworkDetail(widget.homeworkId);
      setState(() {
        _data = d;
        final rec = d['homework']?['my_record'];
        if (rec != null && rec['text_content'] != null) {
          _text.text = rec['text_content'] as String;
        }
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _start() async {
    try {
      final r = await StudentApi.instance.startHomework(widget.homeworkId);
      if (!mounted) return;
      showSnack(
        context,
        r['already_started'] == true ? '已开始过了，继续完成吧' : '开始计时',
      );
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  Future<void> _submit() async {
    if (_text.text.trim().isEmpty) {
      showSnack(context, '请填写作答内容', error: true);
      return;
    }
    setState(() => _submitting = true);
    try {
      final r = await StudentApi.instance.submitHomework(
        widget.homeworkId,
        text: _text.text.trim(),
      );
      if (!mounted) return;
      final rec = r['record'] as Map<String, dynamic>;
      showSnack(context, '提交成功，获得 ${rec['points']} 积分');
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hw = _data?['homework'] as Map<String, dynamic>?;
    final rec = (hw?['my_record'] as Map<String, dynamic>?);
    final started = rec?['start_time'] != null;
    final submitted = rec?['submit_time'] != null;

    return Scaffold(
      appBar: AppBar(title: Text(hw?['title'] as String? ?? '作业')),
      body: _loading
          ? const LoadingView()
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _info('科目', hw?['subject'] as String? ?? '未填写'),
                _info('截止时间', _fmt(hw?['deadline'] as String? ?? '')),
                const SizedBox(height: 12),
                if (hw != null && hw['description'] != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Text(hw['description'] as String),
                    ),
                  ),
                if (submitted) ...[
                  HomeworkReviewResult(record: rec!),
                  const SizedBox(height: 12),
                  Card(
                    color: Colors.green.shade50,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('已提交，不可重复提交',
                              style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  color: Colors.green)),
                          const SizedBox(height: 6),
                          Text('用时：${rec['duration_minutes']} 分钟'),
                          Text('积分：${rec['points']} 分'),
                          if (rec['suspicious'] == true)
                            const Padding(
                              padding: EdgeInsets.only(top: 6),
                              child: Text(
                                '⚠ 用时不足 1 分钟，已标记待老师审核',
                                style: TextStyle(color: Colors.orange),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ] else ...[
                  const SizedBox(height: 12),
                  if (!started)
                    FilledButton.icon(
                      onPressed: _start,
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('开始写作业'),
                    )
                  else ...[
                    TextField(
                      controller: _text,
                      maxLines: 10,
                      decoration: const InputDecoration(
                        labelText: '我的作答',
                        border: OutlineInputBorder(),
                        alignLabelWithHint: true,
                      ),
                    ),
                    const SizedBox(height: 12),
                    FilledButton(
                      onPressed: _submitting ? null : _submit,
                      child: _submitting
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('提交作业'),
                    ),
                  ],
                ],
              ],
            ),
    );
  }

  Widget _info(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        SizedBox(
          width: 80,
          child: Text(label, style: TextStyle(color: Colors.grey.shade600)),
        ),
        Expanded(child: Text(value)),
      ],
    ),
  );
}

class HomeworkReviewResult extends StatelessWidget {
  const HomeworkReviewResult({super.key, required this.record});
  final Map<String, dynamic> record;

  @override
  Widget build(BuildContext context) {
    if (record['reviewed_at'] == null) {
      return const Card(child: ListTile(title: Text('老师尚未批改')));
    }
    final comment = (record['review_comment'] as String?)?.trim();
    return Card(child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('老师批改', style: TextStyle(fontWeight: FontWeight.bold)),
        Text('分数：${record['review_score']} 分'),
        Text('评语：${comment == null || comment.isEmpty ? '老师未写评语' : comment}'),
        Text('批改时间：${_fmt(record['reviewed_at'] as String)}'),
        Text('批改积分：${record['review_points'] ?? 0} 分'),
      ]),
    ));
  }
}

String _fmt(String iso) {
  final dt = DateTime.tryParse(iso);
  if (dt == null) return iso;
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)} ${two(dt.hour)}:${two(dt.minute)}';
}