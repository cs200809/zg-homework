/// 学生端：小游戏（数独 + 成语接龙，PRD 5.6）。
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';

class GamesPage extends StatefulWidget {
  const GamesPage({super.key});

  @override
  State<GamesPage> createState() => _GamesPageState();
}

class _GamesPageState extends State<GamesPage> {
  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('游戏中心'),
          bottom: const TabBar(
            tabs: [Tab(text: '数独'), Tab(text: '成语接龙'), Tab(text: '记录')],
          ),
        ),
        body: const TabBarView(
          children: [_SudokuPanel(), _IdiomPanel(), _RecordsPanel()],
        ),
      ),
    );
  }
}

// ---------------- 数独 ----------------

class _SudokuPanel extends StatefulWidget {
  const _SudokuPanel();

  @override
  State<_SudokuPanel> createState() => _SudokuPanelState();
}

class _SudokuPanelState extends State<_SudokuPanel> {
  String? _puzzleId;
  List<List<int>> _given = [];
  List<List<int>> _cells = [];
  String _difficulty = 'easy';
  int? _selectedR;
  int? _selectedC;
  DateTime? _startedAt;

  static const _difficulties = [
    ('easy', '简单', '+5'),
    ('medium', '中等', '+10'),
    ('hard', '困难', '+15'),
  ];

  Future<void> _start(String difficulty) async {
    try {
      final r = await StudentApi.instance.sudokuStart(difficulty);
      if (!mounted) return;
      final board = (r['board'] as List)
          .map((e) => (e as List).map((v) => v as int).toList())
          .toList();
      setState(() {
        _puzzleId = r['puzzle_id'] as String;
        _given = board;
        _cells = board.map((e) => e.toList()).toList();
        _difficulty = difficulty;
        _selectedR = null;
        _selectedC = null;
        _startedAt = DateTime.now();
      });
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  void _input(int v) {
    if (_puzzleId == null || _selectedR == null || _selectedC == null) return;
    final r = _selectedR!, c = _selectedC!;
    if (_given[r][c] != 0) return; // 提示数不可改
    setState(() => _cells[r][c] = v);
  }

  Future<void> _submit(bool success) async {
    if (_puzzleId == null) return;
    final duration = DateTime.now()
        .difference(_startedAt ?? DateTime.now())
        .inSeconds;
    try {
      final r = await StudentApi.instance.sudokuResult(
        _puzzleId!,
        duration,
        success,
        board: success ? _cells : null,
      );
      if (!mounted) return;
      final pts = (r['points'] as int?) ?? 0;
      showSnack(
        context,
        r['success'] == true ? '完成！获得 $pts 积分' : '未完成或答案有误',
      );
      setState(() => _reset());
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  void _reset() {
    _puzzleId = null;
    _given = [];
    _cells = [];
  }

  @override
  Widget build(BuildContext context) {
    if (_puzzleId == null) {
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('选择难度开始数独，服务端保证唯一解。'),
          const SizedBox(height: 16),
          for (final d in _difficulties) ...[
            Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                title: Text(d.$2),
                trailing: Chip(label: Text(d.$3)),
                onTap: () => _start(d.$1),
              ),
            ),
          ],
          const SizedBox(height: 8),
          Card(
            color: Colors.orange.shade50,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                '数独与成语接龙共用「每日游戏合计 20 分」上限',
                style: TextStyle(fontSize: 12),
              ),
            ),
          ),
        ],
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '数独 · ${_difficulties.firstWhere((d) => d.$1 == _difficulty).$2}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Row(
              children: [
                TextButton(onPressed: () => _submit(false), child: const Text('未完成')),
                FilledButton(
                  onPressed: () => _submit(true),
                  child: const Text('提交'),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 12),
        Center(child: _board()),
        const SizedBox(height: 16),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          alignment: WrapAlignment.center,
          children: [
            for (var n = 1; n <= 9; n++)
              SizedBox(
                width: 44,
                child: OutlinedButton(
                  onPressed: () => _input(n),
                  child: Text('$n'),
                ),
              ),
            SizedBox(
              width: 44,
              child: OutlinedButton(
                onPressed: () => _input(0),
                child: const Text('清'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _board() {
    Widget cell(int r, int c) {
      final isGiven = _given[r][c] != 0;
      final active = _selectedR == r && _selectedC == c;
      return GestureDetector(
        onTap: isGiven ? null : () => setState(() { _selectedR = r; _selectedC = c; }),
        child: Container(
          width: 36,
          height: 36,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: active
                ? Colors.blue.shade100
                : isGiven
                ? Colors.grey.shade100
                : Colors.white,
            border: Border.all(
              color: (c % 3 == 2 || r % 3 == 2)
                  ? Colors.black38
                  : Colors.black12,
              width: (c % 3 == 2 || r % 3 == 2) ? 1.5 : 0.5,
            ),
          ),
          child: Text(
            _cells[r][c] == 0 ? '' : '${_cells[r][c]}',
            style: TextStyle(
              fontSize: 17,
              fontWeight: isGiven ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ),
      );
    }

    return Column(
      children: [
        for (var r = 0; r < 9; r++)
          Row(mainAxisSize: MainAxisSize.min, children: [for (var c = 0; c < 9; c++) cell(r, c)]),
      ],
    );
  }
}

// ---------------- 成语接龙 ----------------

class _IdiomPanel extends StatefulWidget {
  const _IdiomPanel();

  @override
  State<_IdiomPanel> createState() => _IdiomPanelState();
}

class _IdiomPanelState extends State<_IdiomPanel> {
  String _sessionId = '';
  Json? _question;
  int _correct = 0;
  int _wrong = 0;
  int _remaining = 60;
  bool _finished = false;
  int? _gained;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    try {
      final r = await StudentApi.instance.idiomStart();
      if (!mounted) return;
      setState(() {
        _sessionId = r['session_id'] as String;
        _remaining = (r['duration_seconds'] as int?) ?? 60;
        _correct = 0;
        _wrong = 0;
        _finished = false;
        _gained = null;
      });
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (!mounted) return;
        setState(() {
          if (_remaining <= 1) {
            _remaining = 0;
            _finish();
          } else {
            _remaining--;
          }
        });
      });
      await _next();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    }
  }

  Future<void> _next() async {
    if (_sessionId.isEmpty) return;
    try {
      final r = await StudentApi.instance.idiomQuestion(_sessionId);
      if (!mounted) return;
      setState(() {
        _question = r['question'] as Map<String, dynamic>;
        _remaining = (r['remaining_seconds'] as int?) ?? _remaining;
      });
    } catch (e) {
      if (mounted) {
        showSnack(context, errorMessage(e), error: true);
        await _finish();
      }
    }
  }

  Future<void> _answer(String answer) async {
    try {
      final r = await StudentApi.instance.idiomAnswer(_sessionId, answer);
      if (!mounted) return;
      setState(() {
        _correct = (r['correct_count'] as int?) ?? 0;
        _wrong = (r['wrong_count'] as int?) ?? 0;
        _remaining = (r['remaining_seconds'] as int?) ?? _remaining;
      });
      showSnack(
        context,
        r['correct'] == true
            ? '答对了！'
            : '答错了，正确答案是「${r['right_answer']}」',
        error: r['correct'] != true,
      );
      await _next();
    } catch (e) {
      if (mounted) {
        showSnack(context, errorMessage(e), error: true);
        await _finish();
      }
    }
  }

  Future<void> _finish() async {
    _timer?.cancel();
    if (_sessionId.isEmpty) return;
    try {
      final r = await StudentApi.instance.idiomResult(_sessionId);
      if (!mounted) return;
      setState(() {
        _finished = true;
        _gained = (r['points'] as int?) ?? 0;
        _question = null;
      });
    } catch (_) {
      if (mounted) setState(() => _finished = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_finished) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.emoji_events, size: 56, color: Colors.amber),
              const SizedBox(height: 12),
              Text('闯关结束', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text('答对 $_correct 题，答错 $_wrong 题'),
              const SizedBox(height: 8),
              Text(
                '获得 $_gained 积分',
                style: const TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: Colors.amber,
                ),
              ),
              const SizedBox(height: 24),
              FilledButton(onPressed: _start, child: const Text('再来一局')),
            ],
          ),
        ),
      );
    }

    if (_sessionId.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.timeline, size: 56, color: Colors.blue),
              const SizedBox(height: 12),
              const Text('60 秒限时闯关，答对一题得 1 分'),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _start,
                icon: const Icon(Icons.play_arrow),
                label: const Text('开始闯关'),
              ),
            ],
          ),
        ),
      );
    }

    final options = (_question?['options'] as List?) ?? [];

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Chip(
                label: Text('剩余 $_remaining 秒'),
                backgroundColor:
                    (_remaining <= 10 ? Colors.red : Colors.blue).withValues(alpha: .15),
                side: BorderSide.none,
              ),
              Row(
                children: [
                  Chip(
                    label: Text('对 $_correct'),
                    backgroundColor: Colors.green.withValues(alpha: .15),
                    side: BorderSide.none,
                  ),
                  const SizedBox(width: 6),
                  Chip(
                    label: Text('错 $_wrong'),
                    backgroundColor: Colors.red.withValues(alpha: .15),
                    side: BorderSide.none,
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          LinearProgressIndicator(value: (60 - _remaining) / 60),
          const SizedBox(height: 32),
          Text(
            _question?['prompt'] as String? ?? '……',
            style: Theme.of(context).textTheme.headlineSmall,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          for (final opt in options)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => _answer(opt),
                  child: Text(opt as String),
                ),
              ),
            ),
          const Spacer(),
          TextButton(onPressed: _finish, child: const Text('提前结束')),
        ],
      ),
    );
  }
}

// ---------------- 游戏记录 ----------------

class _RecordsPanel extends StatefulWidget {
  const _RecordsPanel();

  @override
  State<_RecordsPanel> createState() => _RecordsPanelState();
}

class _RecordsPanelState extends State<_RecordsPanel> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await StudentApi.instance.gameRecords();
      if (mounted) {
        setState(() {
          _rows = ((r['list'] as List?) ?? [])
              .map((e) => e as Map<String, dynamic>)
              .toList();
        });
      }
    } catch (_) {
      // 忽略：展示空列表
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const LoadingView();
    if (_rows.isEmpty) return const EmptyView(message: '还没有游戏记录');
    return ListView.builder(
      padding: const EdgeInsets.all(12),
      itemCount: _rows.length,
      itemBuilder: (context, i) {
        final r = _rows[i];
        final isSudoku = r['game_type'] == 'sudoku';
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            leading: Icon(isSudoku ? Icons.grid_on : Icons.timeline),
            title: Text(isSudoku ? '数独' : '成语接龙'),
            subtitle: Text(
              '用时 ${r['duration_seconds']} 秒'
              '${r['difficulty'] == null ? '' : ' · 难度 ${r['difficulty']}'}',
            ),
            trailing: Chip(
              label: Text('${r['points'] ?? 0} 分'),
              backgroundColor: Colors.amber.withValues(alpha: .15),
              side: BorderSide.none,
            ),
          ),
        );
      },
    );
  }
}