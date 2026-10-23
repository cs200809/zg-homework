/// 学生端：首页（签到、积分概览、今日作业）+ 底部导航框架。
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/apis.dart';
import '../../core/models.dart';
import '../../state/auth_state.dart';
import '../../widgets/common.dart';
import 'games_page.dart';
import 'reading_page.dart';
import 'homework_page.dart';
import '../common/profile_page.dart';

class StudentHome extends StatefulWidget {
  const StudentHome({super.key});

  @override
  State<StudentHome> createState() => _StudentHomeState();
}

class _StudentHomeState extends State<StudentHome> {
  int _tab = 0;

  static const _tabs = [
    (icon: Icons.home_outlined, active: Icons.home, label: '首页'),
    (icon: Icons.assignment_outlined, active: Icons.assignment, label: '作业'),
    (icon: Icons.book_outlined, active: Icons.book, label: '阅读'),
    (icon: Icons.sports_esports_outlined, active: Icons.sports_esports, label: '游戏'),
    (icon: Icons.person_outline, active: Icons.person, label: '我的'),
  ];

  @override
  Widget build(BuildContext context) {
    final pages = [
      const _StudentOverview(),
      const HomeworkPage(),
      const ReadingPage(),
      const GamesPage(),
      const ProfilePage(),
    ];

    return Scaffold(
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: [
          for (final t in _tabs)
            NavigationDestination(
              icon: Icon(t.icon),
              selectedIcon: Icon(t.active),
              label: t.label,
            ),
        ],
      ),
    );
  }
}

/// 学生首页概览
class _StudentOverview extends StatefulWidget {
  const _StudentOverview();

  @override
  State<_StudentOverview> createState() => _StudentOverviewState();
}

class _StudentOverviewState extends State<_StudentOverview> {
  Json? _summary;
  Json? _checkin;
  Json? _today;
  int _myRank = 0;
  bool _loading = true;
  String? _error;
  bool _checkingIn = false;

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
      final results = await Future.wait([
        StudentApi.instance.pointSummary(),
        StudentApi.instance.checkinStatus(),
        StudentApi.instance.todayHomework(),
        StudentApi.instance.rank('day', size: 50),
      ]);
      setState(() {
        _summary = results[0];
        _checkin = results[1];
        _today = results[2];
        _myRank = (results[3]['my_rank'] as int?) ?? 0;
      });
    } catch (e) {
      setState(() => _error = errorMessage(e));
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _doCheckin() async {
    setState(() => _checkingIn = true);
    try {
      final r = await StudentApi.instance.checkin();
      if (!mounted) return;
      if (r['already_checked'] == true) {
        showSnack(context, '今天已经签到过啦');
      } else {
        final bonus = r['streak_bonus'] ?? 0;
        showSnack(
          context,
          bonus > 0
              ? '签到成功 +${r['points']} 分，连签奖励 +$bonus 分'
              : '签到成功 +${r['points']} 分',
        );
      }
      await _load();
    } catch (e) {
      if (mounted) showSnack(context, errorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _checkingIn = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthState>().user;
    final checkedIn = _checkin?['checked_in'] == true;
    final streak = (_checkin?['streak'] as int?) ?? 0;

    return Scaffold(
      appBar: AppBar(
        title: Text('你好，${user?.nickname ?? user?.username ?? ''}'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const LoadingView()
          : _error != null
          ? ErrorView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  // 积分概览
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '当前积分',
                          value: '${_summary?['total_points'] ?? 0}',
                          suffix: '分',
                          color: Colors.amber.shade700,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: StatCard(
                          label: '今日获得',
                          value: '${_summary?['gained_today'] ?? 0}',
                          suffix: '分',
                          color: Colors.green,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: StatCard(
                          label: '连续签到',
                          value: '$streak',
                          suffix: '天',
                          color: Colors.orange,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: StatCard(
                          label: '今日排名',
                          value: _myRank > 0 ? '$_myRank' : '—',
                          suffix: _myRank > 0 ? '名' : '',
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // 签到卡片
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  checkedIn ? '今日已签到' : '每日签到',
                                  style: Theme.of(context).textTheme.titleMedium,
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  checkedIn
                                      ? '获得 ${_checkin?['points']} 分'
                                      : '签到得 5 分，连续 7 天额外 +10 分',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                          FilledButton(
                            onPressed: checkedIn || _checkingIn ? null : _doCheckin,
                            child: Text(checkedIn ? '已签到' : '签到'),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // 今日作业
                  Text('今日作业', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  _buildHomeworkList(),
                ],
              ),
            ),
    );
  }

  Widget _buildHomeworkList() {
    final list = (_today?['list'] as List?) ?? [];
    if (list.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: EmptyView(message: '今天没有作业'),
      );
    }
    return Column(
      children: list.map((e) {
        final hw = e as Map<String, dynamic>;
        final status = hw['my_status'] as String? ?? 'not_started';
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            title: Text(hw['title'] as String? ?? ''),
            subtitle: hw['subject'] == null
                ? null
                : Text('${hw['subject']} · 截止 ${_fmtDateTime(hw['deadline'] as String)}'),
            trailing: Chip(
              label: Text(
                homeworkStatusLabel[status] ?? status,
                style: const TextStyle(fontSize: 11),
              ),
              visualDensity: VisualDensity.compact,
              backgroundColor: (homeworkStatusColor[status] ?? Colors.grey).withValues(alpha: .12),
              side: BorderSide.none,
            ),
            onTap: () => Navigator.of(context).pushNamed('/homework/${hw['id']}'),
          ),
        );
      }).toList(),
    );
  }
}

String _fmtDateTime(String iso) {
  final dt = DateTime.tryParse(iso);
  if (dt == null) return iso;
  String two(int v) => v.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)} ${two(dt.hour)}:${two(dt.minute)}';
}