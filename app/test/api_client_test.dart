import 'dart:convert';

import 'package:finsight/api/api_client.dart';
import 'package:finsight/data/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Txn sample() => Txn(
      id: 7,
      ts: DateTime.utc(2026, 9, 12, 4, 30),
      amountPaise: 48500,
      direction: 'debit',
      merchantRaw: 'SWIGGY',
      merchantNorm: 'swiggy',
      merchantKey: 'swiggy',
      displayName: 'Swiggy',
      merchantKind: 'known',
      mode: 'upi',
      descriptor: '',
      categoryId: 'food',
      categorySource: 'rule',
      isSelfTransfer: false,
      isRefund: false,
    );

void main() {
  const config = ServerConfig(baseUrl: 'https://laptop:8443/', token: 'tok', fingerprint: 'ab');

  test('sends only the allowed fields, with the token', () async {
    late Map<String, dynamic> sent;
    final client = MockClient((req) async {
      expect(req.url.toString(), 'https://laptop:8443/v1/insights');
      expect(req.headers['Authorization'], 'Bearer tok');
      sent = jsonDecode(req.body) as Map<String, dynamic>;
      return http.Response('{"as_of":"2026-09-20"}', 200);
    });
    await ApiClient(config, client: client).insights([sample()], DateTime(2026, 9, 20));
    final t = (sent['transactions'] as List).single as Map<String, dynamic>;
    expect(t.keys.toSet(), {
      'id', 'ts', 'amount_paise', 'direction', 'merchant_norm', 'category', 'account_alias',
      'mode', 'is_self_transfer', 'is_refund',
    });
    expect(t['ts'], '2026-09-12T04:30:00.000Z');
    expect(sent['as_of'], '2026-09-20');
  });

  test('server errors become ApiException with the server\'s message', () async {
    final client = MockClient((_) async => http.Response(
        '{"error":{"code":"unauthorized","message":"Missing or wrong API token."}}', 401));
    expect(
      () => ApiClient(config, client: client).chat('hi', [], DateTime(2026, 9, 20)),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', 'unauthorized')),
    );
  });

  test('fingerprints are normalised from any format', () {
    expect(normalizeFingerprint('AB:CD:12'), 'abcd12');
  });
}
