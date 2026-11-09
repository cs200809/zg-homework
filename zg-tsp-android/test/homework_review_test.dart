import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zg_tsp_android/pages/student/homework_page.dart';

void main() {
  testWidgets('shows review score, comment, time and points', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: HomeworkReviewResult(record: {
      'review_score': 0, 'review_comment': '继续努力',
      'reviewed_at': '2026-10-30T12:30:00', 'review_points': 5,
    }))));
    expect(find.textContaining('0'), findsWidgets);
    expect(find.textContaining('继续努力'), findsOneWidget);
    expect(find.textContaining('2026-10-30 12:30'), findsOneWidget);
    expect(find.textContaining('5'), findsWidgets);
  });
}
