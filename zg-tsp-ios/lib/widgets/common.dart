/// 通用 UI 组件。
library;

import 'package:flutter/material.dart';

/// 加载态占位
class LoadingView extends StatelessWidget {
  const LoadingView({super.key});

  @override
  Widget build(BuildContext context) =>
      const Center(child: CircularProgressIndicator());
}

/// 空态占位
class EmptyView extends StatelessWidget {
  const EmptyView({super.key, this.message = '暂无数据'});

  final String message;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.inbox_outlined, size: 48, color: Colors.grey.shade300),
        const SizedBox(height: 8),
        Text(message, style: TextStyle(color: Colors.grey.shade500)),
      ],
    ),
  );
}

/// 错误态（带重试）
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.cloud_off_outlined, size: 48, color: Colors.grey.shade300),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          if (onRetry != null) ...[
            const SizedBox(height: 12),
            OutlinedButton(onPressed: onRetry, child: const Text('重试')),
          ],
        ],
      ),
    ),
  );
}

/// 统计卡片（移动端单列/双列自适应）
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.label,
    required this.value,
    this.suffix,
    this.color,
  });

  final String label;
  final String value;
  final String? suffix;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(
                color: Colors.grey.shade600,
              ),
            ),
            const SizedBox(height: 6),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(
                  value,
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: color,
                  ),
                ),
                if (suffix != null) ...[
                  const SizedBox(width: 2),
                  Text(suffix!, style: theme.textTheme.bodySmall),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// 积分类型 → 中文与颜色
const Map<String, String> pointTypeLabel = {
  'checkin': '签到',
  'homework': '作业',
  'reading': '阅读',
  'game': '游戏',
  'consume': '消费',
};

const Map<String, Color> pointTypeColor = {
  'checkin': Colors.green,
  'homework': Colors.blue,
  'reading': Colors.purple,
  'game': Colors.orange,
  'consume': Colors.red,
};

/// 作业状态 → 中文与颜色
const Map<String, String> homeworkStatusLabel = {
  'not_started': '未开始',
  'doing': '进行中',
  'submitted': '已提交',
  'late': '迟交',
};

const Map<String, Color> homeworkStatusColor = {
  'not_started': Colors.grey,
  'doing': Colors.blue,
  'submitted': Colors.green,
  'late': Colors.orange,
};

/// 顶部提示条
void showSnack(BuildContext context, String message, {bool error = false}) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? Colors.red.shade600 : null,
        behavior: SnackBarBehavior.floating,
      ),
    );
}