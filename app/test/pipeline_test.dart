import 'dart:io';

import 'package:finsight/data/repository.dart';
import 'package:finsight/ingestion/normalizer.dart';
import 'package:finsight/ingestion/pipeline.dart';
import 'package:finsight/ingestion/sms_parser.dart';
import 'package:finsight/ingestion/sms_source.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

class ListSource implements SmsSource {
  ListSource(this.messages);
  final List<SmsMessage> messages;
  @override
  Future<List<SmsMessage>> since(int millis) async =>
      messages.where((m) => m.receivedAt.millisecondsSinceEpoch > millis).toList();
}

void main() {
  late Repository repo;
  late IngestionPipeline pipeline;

  setUp(() async {
    final rules = loadRules();
    repo = Repository(await openTestDb());
    pipeline = IngestionPipeline(repo, SmsParser(rules.hints), Normalizer(rules, 'test'));
  });

  test('demo data ingests, and a second sync adds nothing', () async {
    final demo = DemoSmsSource(File('assets/demo/demo_sms.jsonl').readAsStringSync());
    final first = await pipeline.syncFrom(demo, tag: 'demo');
    expect(first[IngestStatus.inserted], greaterThan(100));
    await repo.setSetting('checkpoint_demo', null); // force a full re-read
    final second = await pipeline.syncFrom(demo, tag: 'demo');
    expect(second[IngestStatus.inserted], 0);
    expect(second[IngestStatus.duplicate], greaterThanOrEqualTo(first[IngestStatus.inserted]!));
    // No raw message text is stored anywhere.
    final rows = await repo.db.query('transactions');
    expect(rows.first.keys, isNot(contains('body')));
  });

  test('rules categorise known merchants and people; others wait for the model', () async {
    final at = DateTime(2026, 9, 12, 10);
    await pipeline.ingest(SmsMessage('VM-HDFCBK',
        'Money Sent! Rs 485.00 from HDFC Bank A/c **1234 to SWIGGY on 12-09-26. UPI Ref No 512345678901. Not you? Call 18000000000', at));
    await pipeline.ingest(SmsMessage('VM-HDFCBK',
        'Money Sent! Rs 500.00 from HDFC Bank A/c **1234 to RAHUL SHARMA on 12-09-26. UPI Ref No 512345678902. Not you? Call 18000000000', at));
    await pipeline.ingest(SmsMessage('VM-HDFCBK',
        'Money Sent! Rs 60.00 from HDFC Bank A/c **1234 to SRI BALAJI SWEETS on 12-09-26. UPI Ref No 512345678903. Not you? Call 18000000000', at));
    final byName = {for (final t in await repo.recent()) t.displayName: t};
    expect(byName['Swiggy']!.categoryId, 'food');
    expect(byName['Rahul Sharma']!.categoryId, 'transfers');
    expect(byName['Rahul Sharma']!.merchantNorm, startsWith('person:'));
    expect(byName['Sri Balaji Sweets']!.categorySource, 'pending');
  });

  test('a correction applies to the merchant\'s other payments and to new ones', () async {
    final at = DateTime(2026, 9, 12, 10);
    Future<void> pay(String ref, int minute) => pipeline.ingest(SmsMessage('VM-HDFCBK',
        'Money Sent! Rs 30.00 from HDFC Bank A/c **1234 to q123456789@ybl on 12-09-26. UPI Ref No $ref. Not you?',
        at.add(Duration(minutes: minute))));
    await pay('512345678911', 0);
    await pay('512345678912', 5);
    final first = (await repo.recent()).last;
    expect(first.merchantKey, 'vpa:q123456789@ybl');
    await repo.correct(first, 'food');
    await pay('512345678913', 10);
    final all = await repo.recent();
    expect(all.every((t) => t.categoryId == 'food'), isTrue);
  });

  test('money moved between your own accounts is a self transfer', () async {
    final at = DateTime(2026, 9, 20, 21);
    await pipeline.ingest(SmsMessage('VM-HDFCBK',
        'Money Sent! Rs 5000.00 from HDFC Bank A/c **1234 to ROHITH G on 20-09-26. UPI Ref No 600000000001. Not you?', at));
    await pipeline.ingest(SmsMessage('VM-KOTAKB',
        'Received Rs.5000.00 in your Kotak Bank AC X9876 from rohith.g@okaxis on 20-09-26.UPI Ref:600000000001.',
        at.add(const Duration(seconds: 40))));
    final all = await repo.recent();
    expect(all, hasLength(2));
    expect(all.every((t) => t.isSelfTransfer), isTrue);
  });

  test('paying one friend and being repaid by another is not a self transfer', () async {
    final at = DateTime(2026, 9, 21, 13);
    await pipeline.ingest(SmsMessage('VM-HDFCBK',
        'Money Sent! Rs 500.00 from HDFC Bank A/c **1234 to RAHUL SHARMA on 21-09-26. UPI Ref No 600000000002. Not you?', at));
    await pipeline.ingest(SmsMessage('VM-KOTAKB',
        'Received Rs.500.00 in your Kotak Bank AC X9876 from priya.nair@okaxis on 21-09-26.UPI Ref:600000000003.',
        at.add(const Duration(minutes: 5))));
    final all = await repo.recent();
    expect(all, hasLength(2));
    expect(all.any((t) => t.isSelfTransfer), isFalse);
  });

  test('balances from SMS feed safe-to-spend', () async {
    await pipeline.syncFrom(ListSource([
      SmsMessage('VM-HDFCBK', 'Available balance in your A/c XX1234 is Rs 45,000.50 as on 20-09-26. -HDFC Bank',
          DateTime(2026, 9, 20)),
    ]));
    expect(await repo.knownBalance(), 4500050);
  });
}
