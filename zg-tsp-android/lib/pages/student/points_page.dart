/// 学生端：积分明细与排行榜（PRD 5.4）。
library;

import 'package:flutter/material.dart';

import '../../core/apis.dart';
import '../../core/models.dart';
import '../../widgets/common.dart';

class PointsPage extends StatefulWidget {
  const PointsPage({super.key});

  @override
  State<PointsPage> createState() => _PointsPageState();
}

class _PointsPageState extends State<PointsPage> {
  int _tab = 0;

  static const _tabs = ['明细', '今日榜', '总榜'];

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      initialIndex: _tab,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('我的积分'),
          bottom: TabBar(
            onTap: (i) => setState(() => _tab = i),
            tabs: _tabs.map((t) => Tab(text: t)).toList(),
          ),
        ),
        body: const TabBarView(
          children: [_PointLogPanel(), _RankPanel('day'), _RankPanel('total')],
        ),
      ),
    );
  }
}

class _PointLogPanel extends StatefulWidget {
  const _PointLogPanel();

  @override
  State<_PointLogPanel> createState() => _PointLogPanelState();
}

class _PointLogPanelState extends State<_PointLogPanel> {
  Json? _summary;
  List<Map<String, dynamic>> _rows = [];
  int _page = 1;
  int _total = 0;
  bool _loading = true;
  String? _filter;

  static const _filters = ['checkin', 'homework', 'reading', 'game', 'consume'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        StudentApi.instance.pointSummary(),
        StudentApi.instance.pointLog(page: _page, type: _filter),
      ]);
      setState(() {
        _summary = results[0];
        _rows = ((results[1]['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
        _total = (results[1]['total'] as int?) ?? 0;
      });
    } catch (_) {
      // 忽略：保持空列表
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Expanded(
                child: StatCard(
                  label: '当前积分',
                  value: '${_summary?['total_points'] ?? 0}',
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
        ),
        SizedBox(
          height: 40,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            children: [
              ChoiceChip(
                label: const Text('全部'),
                selected: _filter == null,
                onSelected: (_) {
                  setState(() {
                    _filter = null;
                    _page = 1;
                  });
                  _load();
                },
              ),
              for (final f in _filters)
                Padding(
                  padding: const EdgeInsets.only(left: 6),
                  child: ChoiceChip(
                    label: Text(pointTypeLabel[f] ?? f),
                    selected: _filter == f,
                    onSelected: (_) {
                      setState(() {
                        _filter = f;
                        _page = 1;
                      });
                      _load();
                    },
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: _loading
              ? const LoadingView()
              : _rows.isEmpty
              ? const EmptyView(message: '暂无积分记录')
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    itemCount: _rows.length,
                    itemBuilder: (context, i) {
                      final r = _rows[i];
                      final type = r['type'] as String? ?? '';
                      final pts = (r['points'] as int?) ?? 0;
                      return Card(
                        margin: const EdgeInsets.only(bottom: 6),
                        child: ListTile(
                          dense: true,
                          leading: Chip(
                            label: Text(pointTypeLabel[type] ?? type),
                            backgroundColor:
                                (pointTypeColor[type] ?? Colors.grey).withValues(alpha: .15),
                            side: BorderSide.none,
                          ),
                          title: Text('${r['remark'] ?? '-'}'),
                          subtitle: Text('${r['log_date'] ?? ''}'),
                          trailing: Text(
                            '${pts > 0 ? '+' : ''}$pts',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: pts >= 0 ? Colors.green : Colors.red,
                            ),
                          ),
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
    );
  }
}

class _RankPanel extends StatefulWidget {
  const _RankPanel(this.type);

  final String type; // day / total

  @override
  State<_RankPanel> createState() => _RankPanelState();
}

class _RankPanelState extends State<_RankPanel> {
  List<Map<String, dynamic>> _rows = [];
  int _myRank = 0;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await StudentApi.instance.rank(widget.type);
      if (!mounted) return;
      setState(() {
        _rows = ((r['list'] as List?) ?? [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
        _myRank = (r['my_rank'] as int?) ?? 0;
      });
    } catch (_) {
      // 忽略
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const LoadingView();
    return Column(
      children: [
        if (_myRank > 0)
          Container(
            width: double.infinity,
            color: Colors.amber.shade50,
            padding: const EdgeInsets.all(12),
            child: Text(
              '我的排名：第 $_myRank 名${_myRank > 50 ? '（不在前 50，继续加油）' : ''}',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
        Expanded(
          child: _rows.isEmpty
              ? const EmptyView(message: '暂无排行数据')
              : ListView.builder(
                  itemCount: _rows.length,
                  itemBuilder: (context, i) {
                    final r = _rows[i];
                    final rank = (r['rank'] as int?) ?? 0;
                    final medal = rank <= 3
                        ? [Colors.amber, Colors.grey, Colors.brown.shade600][rank - 1]
                        : null;
                    return ListTile(
                      dense: true,
                      leading: CircleAvatar(
                        radius: 16,
                        backgroundColor: medal?.withValues(alpha: .2),
                        child: Text(
                          '$rank',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: medal,
                          ),
                        ),
                      ),
                      title: Text(r['nickname'] as String? ?? r['username'] as String? ?? ''),
                      trailing: Text(
                        '${r['points']} 分',
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}