/// zg-tsp-ios 应用入口 —— P0 骨架占位。
/// 页面与路由在 P8 阶段接入（PRD 第 11 节）。
library;

import 'package:flutter/material.dart';

void main() {
  runApp(const ZgTspApp());
}

class ZgTspApp extends StatelessWidget {
  const ZgTspApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'zg-tsp',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1677FF)),
        useMaterial3: true,
      ),
      home: const Scaffold(
        body: Center(child: Text('zg-tsp iOS 客户端')),
      ),
    );
  }
}