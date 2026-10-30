/// 学生端：课后阅读（PRD 5.5）。
///
/// 防挂机：每 30 秒上报心跳；App 切到后台时暂停计时并停止上报，
/// 服务端校验间隔 30s±10s，异常不计分（PRD 5.5）。
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/config.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';

/// 心跳间隔（秒），与 PRD 5.5 一致
const kHeartbeatSeconds = 30;

class ReadingPage extends StatefulWidget {
  const ReadingPage({super.key});

  @override
  State<ReadingPage> createState() => _ReadingPageState();
}

class _ReadingPageState extends State<ReadingPage> {
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
      final data = await StudentApi.instance.articleList();
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
      appBar: AppBar(title: const Text('课后阅读')),
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
          child: const EmptyView(message: '暂无文章'),
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final a = list[i] as Map<String, dynamic>;
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            title: Text(a['title'] as String? ?? ''),
            subtitle: Text(
              a['created_role'] == 'admin' ? '管理员发布' : '老师发布',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ArticleReaderPage(articleId: a['id'] as int),
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

/// 文章阅读页：计时 + 心跳 + 读完标记
class ArticleReaderPage extends StatefulWidget {
  const ArticleReaderPage({super.key, required this.articleId});

  final int articleId;

  @override
  State<ArticleReaderPage> createState() => _ArticleReaderPageState();
}

class _ArticleReaderPageState extends State<ArticleReaderPage>
    with WidgetsBindingObserver {
  Json? _article;
  bool _loading = true;
  Timer? _heartbeat;
  int _elapsed = 0;
  int _points = 0;
  bool _finished = false;
  /// 前台且在阅读中才上报心跳
  bool _active = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _heartbeat?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 切后台暂停计时（PRD 5.5）
    setState(() => _active = state == AppLifecycleState.resumed);
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final d = await StudentApi.instance.articleDetail(widget.articleId);
      setState(() {
        _article = d['article'] as Map<String, dynamic>?;
        final rec = _article?['my_record'] as Map<String, dynamic>?;
        if (rec != null) {
          _elapsed = (rec['duration_seconds'] as int?) ?? 0;
          _points = (rec['points'] as int?) ?? 0;
          _finished = (rec['finished'] as bool?) ?? false;
        }
      });
      _startHeartbeat();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(
      const Duration(seconds: kHeartbeatSeconds),
      (_) => _report(),
    );
  }

  Future<void> _report() async {
    if (!_active || _finished) return; // 后台或已读完则不上报
    try {
      final r = await StudentApi.instance.heartbeat(widget.articleId, kHeartbeatSeconds);
      if (!mounted) return;
      setState(() {
        _elapsed = (r['duration_seconds'] as int?) ?? _elapsed;
        _points = (r['points'] as int?) ?? _points;
      });
      if (r['accepted'] != true && mounted) {
        showSnack(context, r['reason'] ?? '本次计时未采纳');
      }
    } catch (_) {
      // 网络异常：等下一个心跳，不打断阅读
    }
  }

  Future<void> _finish() async {
    if (_finished) return;
    try {
      final r = await StudentApi.instance.finishArticle(widget.articleId);
      if (!mounted) return;
      setState(() {
        _finished = true;
        _points = (r['points'] as int?) ?? _points;
      });
      _heartbeat?.cancel();
      if (r['already_finished'] == true) {
        showSnack(context, '本篇已读过了');
      } else {
        showSnack(context, '恭喜读完，获得 ${r['points_gained']} 积分');
      }
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  /// 导出 PDF（迭代 v2.1）：服务端生成，用系统浏览器/阅读器打开
  Future<void> _exportPdf() async {
    try {
      final r = await StudentApi.instance.exportPdf(widget.articleId);
      final path = (r['file_url'] as String?) ?? '';
      if (path.isEmpty) throw Exception('未返回文件地址');
      final url = '${AppConfig.apiBaseUrl}$path';
      final opened = await launchUrl(
        Uri.parse(url),
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
    final a = _article;
    final minutes = _elapsed ~/ 60;
    final seconds = _elapsed % 60;

    return Scaffold(
      appBar: AppBar(
        title: Text(a?['title'] as String? ?? '阅读'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(28),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '已阅读 $minutes:${seconds.toString().padLeft(2, '0')}',
                  style: const TextStyle(fontSize: 12),
                ),
                const SizedBox(width: 12),
                Text('$_points 分', style: const TextStyle(fontSize: 12)),
                if (_finished) ...[
                  const SizedBox(width: 12),
                  const Text(
                    '已读完',
                    style: TextStyle(fontSize: 12, color: Colors.green),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
      body: _loading
          ? const LoadingView()
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  color: Colors.blue.shade50,
                  child: const Padding(
                    padding: EdgeInsets.all(12),
                    child: Text(
                      '每读满 1 分钟得 1 分，单篇最多 10 分、每日最多 30 分；读完再得 5 分。\n'
                      '切到后台会暂停计时。',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                SelectableText(
                  a?['content'] as String? ?? '',
                  style: const TextStyle(height: 1.9, fontSize: 15),
                ),
                const SizedBox(height: 32),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton(
                        onPressed: _finished ? null : _finish,
                        child: Text(_finished ? '本篇已读完' : '我已读完全文'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    OutlinedButton.icon(
                      onPressed: _exportPdf,
                      icon: const Icon(Icons.picture_as_pdf_outlined),
                      label: const Text('导出 PDF'),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                const Text(
                  '本文为只读内容，不可编辑。',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
    );
  }
}