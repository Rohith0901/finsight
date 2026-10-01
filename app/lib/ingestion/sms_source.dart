// Where SMS come from: the phone's inbox (our own Kotlin channel, see
// android/app/src/main/kotlin/.../MainActivity.kt) or the bundled demo set.
//
// There is no background receiver (ADR-002): the app catches up from the inbox
// whenever it opens or is told the inbox changed, so nothing is missed even if
// Android stops background work.

import 'dart:convert';

import 'package:flutter/services.dart';

class SmsMessage {
  const SmsMessage(this.sender, this.body, this.receivedAt);
  final String sender;
  final String body;
  final DateTime receivedAt;
}

abstract class SmsSource {
  Future<List<SmsMessage>> since(int millis);
}

class InboxSmsSource implements SmsSource {
  static const _channel = MethodChannel('finsight/sms');
  static const _events = EventChannel('finsight/sms_events');

  Future<bool> hasPermission() async =>
      await _channel.invokeMethod<bool>('hasPermission') ?? false;

  Future<bool> requestPermission() async =>
      await _channel.invokeMethod<bool>('requestPermission') ?? false;

  /// Fires when the SMS inbox changes while the app is open.
  Stream<void> get changes => _events.receiveBroadcastStream().map((_) {});

  @override
  Future<List<SmsMessage>> since(int millis) async {
    final out = <SmsMessage>[];
    var cursor = millis;
    while (true) {
      final batch = await _channel.invokeListMethod<Map<dynamic, dynamic>>(
              'readInbox', {'since': cursor, 'limit': 500}) ??
          const [];
      for (final m in batch) {
        out.add(SmsMessage(m['address'] as String? ?? '', m['body'] as String? ?? '',
            DateTime.fromMillisecondsSinceEpoch(m['date'] as int)));
      }
      if (batch.length < 500) break;
      cursor = batch.last['date'] as int;
    }
    return out;
  }
}

/// Three months of one synthetic user's messages, shifted so the newest is today.
class DemoSmsSource implements SmsSource {
  DemoSmsSource(this.jsonl, {DateTime? now}) : now = now ?? DateTime.now();
  final String jsonl;
  final DateTime now;

  @override
  Future<List<SmsMessage>> since(int millis) async {
    final rows = [
      for (final line in const LineSplitter().convert(jsonl))
        if (line.trim().isNotEmpty) jsonDecode(line) as Map<String, dynamic>,
    ];
    if (rows.isEmpty) return [];
    final times = rows.map((r) => DateTime.parse(r['received_at'] as String)).toList();
    final newest = times.reduce((a, b) => a.isAfter(b) ? a : b);
    final shift = DateTime(now.year, now.month, now.day)
        .difference(DateTime(newest.year, newest.month, newest.day));
    return [
      for (var i = 0; i < rows.length; i++)
        if (times[i].add(shift).millisecondsSinceEpoch > millis)
          SmsMessage(rows[i]['sender'] as String, rows[i]['body'] as String, times[i].add(shift)),
    ];
  }
}

Future<String> loadDemoAsset() => rootBundle.loadString('assets/demo/demo_sms.jsonl');
