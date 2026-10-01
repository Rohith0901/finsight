// Runs every fixture in shared/fixtures/sms_synthetic.jsonl (and sms_real.jsonl
// when the team has added real, masked messages) through the parser.
//
// The synthetic formats were written by the same team as the parser, so passing
// them proves consistency, not real-world accuracy. sms_real.jsonl is the real test.

import 'dart:convert';
import 'dart:io';

import 'package:finsight/ingestion/sms_parser.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

List<String> diff(SmsParser parser, Map<String, dynamic> line) {
  final exp = line['expected'] as Map<String, dynamic>;
  final got = parser.parse(line['sender'] as String, line['body'] as String);
  if (got.outcome.name != exp['outcome']) {
    return ['outcome ${got.outcome.name}(${got.reason}) != ${exp['outcome']}'];
  }
  final have = <String, Object?>{
    'amount_paise': got.amountPaise,
    'direction': got.direction,
    'account_mask': got.accountMask,
    'card': got.card,
    'merchant_raw': got.merchantRaw?.toLowerCase(),
    'mode': got.mode,
    'ref_no': got.refNo,
    'balance_paise': got.balancePaise,
    'available_limit_paise': got.availableLimitPaise,
    'is_refund': got.isRefund,
    'is_card_bill': got.isCardBill,
    'p2a': got.p2a,
    'p2m': got.p2m,
    'hints': got.hints.join(','),
  };
  final keys = exp['outcome'] == 'transaction'
      ? have.keys
      : (exp['outcome'] == 'balance' ? ['account_mask', 'balance_paise'] : const <String>[]);
  final out = <String>[];
  for (final k in keys) {
    if (!exp.containsKey(k)) continue;
    var want = exp[k];
    if (k == 'merchant_raw' && want is String) want = want.toLowerCase();
    if (k == 'hints') want = (want as List).join(',');
    if (want != have[k]) out.add('$k: ${have[k]} != $want');
  }
  return out;
}

void runFixtures(String path) {
  final file = File(path);
  if (!file.existsSync()) return;
  test('parses every message in $path', () {
    final parser = SmsParser(loadRules().hints);
    final failures = <String>[];
    var n = 0;
    for (final raw in file.readAsLinesSync()) {
      if (raw.trim().isEmpty) continue;
      n++;
      final line = jsonDecode(raw) as Map<String, dynamic>;
      final d = diff(parser, line);
      if (d.isNotEmpty) failures.add('${line['template']}: $d\n    ${line['body']}');
    }
    expect(n, greaterThan(0));
    expect(failures, isEmpty, reason: '${failures.length}/$n failed:\n${failures.take(20).join('\n')}');
  });
}

void main() {
  runFixtures('../shared/fixtures/sms_synthetic.jsonl');
  runFixtures('../shared/fixtures/sms_real.jsonl');

  final parser = SmsParser(loadRules().hints);

  test('amounts in every format', () {
    expect(toPaise('1,23,456.78'), 12345678);
    expect(toPaise('485.0'), 48500);
    expect(toPaise('485'), 48500);
    expect(toPaise('25000.5'), 2500050);
  });

  test('a debit alert that also says "never share OTP" is still a transaction', () {
    final p = parser.parse('VM-HDFCBK',
        'Rs.250.00 debited from HDFC Bank A/c **1234 to SWIGGY on 01-10-26. UPI Ref No 512345678901. Never share your OTP.');
    expect(p.outcome, Outcome.transaction);
    expect(p.amountPaise, 25000);
    expect(p.refNo, '512345678901');
  });

  test('personal senders are skipped before reading the body', () {
    expect(parser.parse('+919876543210', 'Rs 500 debited lol').outcome, Outcome.skipped);
  });

  test('requests, reminders and declines are not transactions', () {
    for (final body in [
      'RAHUL has requested money from you. On approving, Rs 500 will be debited.',
      'Payment of Rs 4,000 is due on your Credit Card XX1234 by 05-10-26.',
      'Transaction of Rs 999 at MYNTRA declined due to insufficient balance.',
    ]) {
      expect(parser.parse('VM-HDFCBK', body).outcome, Outcome.rejected, reason: body);
    }
  });
}
