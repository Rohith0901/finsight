import 'dart:convert';

import 'package:finsight/ingestion/normalizer.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  // The same cases ml/finsight_ml/names.py must pass: both sides agree on keys.
  test('matches every shared merchant-name case', () {
    final data = jsonDecode(sharedFile('fixtures/merchant_name_cases.json')) as Map<String, dynamic>;
    final n = Normalizer(loadRules(), data['salt'] as String);
    for (final c in (data['cases'] as List).cast<Map<String, dynamic>>()) {
      final got = n.resolve(c['raw'] as String, p2a: c['p2a'] as bool, p2m: c['p2m'] as bool);
      final exp = c['expected'] as Map<String, dynamic>;
      expect([got.kind, got.key, got.category], [exp['kind'], exp['key'], exp['category']],
          reason: c['raw'] as String);
      expect(n.isCardBillName(c['raw'] as String), exp['card_bill'], reason: c['raw'] as String);
    }
  });

  test('pseudonyms are stable per phone and differ between phones', () {
    final rules = loadRules();
    final a = Normalizer(rules, 'salt-a');
    expect(a.resolve('RAHUL SHARMA').key, a.resolve('Rahul Sharma').key);
    expect(a.resolve('RAHUL SHARMA').key, isNot(Normalizer(rules, 'salt-b').resolve('RAHUL SHARMA').key));
  });
}
