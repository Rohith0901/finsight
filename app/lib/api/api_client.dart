// Client for the stateless FinSight API (docs/api.md).
//
// HTTPS with a pinned certificate: the laptop's self-signed certificate is
// accepted only if its SHA-256 fingerprint matches the one in Settings, so the
// laptop's IP address can change without a new certificate.

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

import '../data/models.dart';

class ApiException implements Exception {
  ApiException(this.code, this.message, [this.status]);
  final String code;
  final String message;
  final int? status;
  @override
  String toString() => 'ApiException($code, $message)';
}

class ServerConfig {
  const ServerConfig({required this.baseUrl, required this.token, required this.fingerprint});
  final String baseUrl; // e.g. https://192.168.1.20:8443
  final String token;
  final String fingerprint; // lowercase hex SHA-256 of the certificate (scripts/gen_cert.sh)

  bool get isComplete => baseUrl.isNotEmpty && token.isNotEmpty && fingerprint.isNotEmpty;
}

String normalizeFingerprint(String f) => f.replaceAll(RegExp(r'[^0-9a-fA-F]'), '').toLowerCase();

http.Client pinnedClient(String fingerprint) {
  final want = normalizeFingerprint(fingerprint);
  final inner = HttpClient()
    ..connectionTimeout = const Duration(seconds: 8)
    ..badCertificateCallback =
        (X509Certificate cert, String host, int port) => sha256.convert(cert.der).toString() == want;
  return IOClient(inner);
}

String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

class ApiClient {
  ApiClient(this.config, {http.Client? client})
      : _client = client ?? pinnedClient(config.fingerprint);

  final ServerConfig config;
  final http.Client _client;

  Uri _uri(String path) => Uri.parse('${config.baseUrl.replaceAll(RegExp(r'/+$'), '')}$path');

  Future<Map<String, dynamic>> _post(String path, Map<String, Object?> body) async {
    final http.Response r;
    try {
      r = await _client
          .post(_uri(path),
              headers: {
                'Authorization': 'Bearer ${config.token}',
                'Content-Type': 'application/json',
              },
              body: jsonEncode(body))
          .timeout(const Duration(seconds: 45));
    } catch (e) {
      // Includes ArgumentError for an address without https://.
      throw ApiException('unreachable', 'Could not reach the server (${e.runtimeType}).');
    }
    Object? decoded;
    try {
      decoded = r.body.isEmpty ? <String, dynamic>{} : jsonDecode(r.body);
    } on FormatException {
      decoded = null; // e.g. a proxy's HTML error page
    }
    if (r.statusCode != 200) {
      final err = decoded is Map<String, dynamic> ? decoded['error'] : null;
      throw ApiException(
        err is Map ? '${err['code']}' : 'http_${r.statusCode}',
        err is Map ? '${err['message']}' : 'Server answered ${r.statusCode}.',
        r.statusCode,
      );
    }
    if (decoded is! Map<String, dynamic>) {
      throw ApiException('bad_response', 'Server answered ${r.statusCode} with something unexpected.',
          r.statusCode);
    }
    return decoded;
  }

  Future<bool> health() async {
    try {
      final r = await _client.get(_uri('/healthz')).timeout(const Duration(seconds: 8));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// One request per batch of up to 500 pending transactions.
  Future<List<Map<String, dynamic>>> classify(List<Txn> txns) async {
    final out = <Map<String, dynamic>>[];
    for (var i = 0; i < txns.length; i += 500) {
      final batch = txns.sublist(i, i + 500 > txns.length ? txns.length : i + 500);
      final r = await _post('/v1/classify', {
        'items': [
          for (final t in batch)
            {
              'id': '${t.id}',
              'merchant_norm': t.merchantNorm,
              'descriptor': t.descriptor,
              'mode': t.mode,
              'direction': t.direction,
              'amount_paise': t.amountPaise,
            },
        ],
      });
      out.addAll((r['items'] as List).cast<Map<String, dynamic>>());
    }
    return out;
  }

  Future<Map<String, dynamic>> insights(List<Txn> window, DateTime asOf,
          {int? balancePaise, int savingsTargetPaise = 0}) =>
      _post('/v1/insights', {
        'transactions': [for (final t in window) t.toApi()],
        'as_of': isoDate(asOf),
        'balance_paise': balancePaise,
        'savings_target_paise': savingsTargetPaise,
      });

  Future<Map<String, dynamic>> chat(String question, List<Txn> window, DateTime asOf,
          {int? balancePaise, int savingsTargetPaise = 0, String provider = 'auto'}) =>
      _post('/v1/chat', {
        'question': question,
        'transactions': [for (final t in window) t.toApi()],
        'as_of': isoDate(asOf),
        'balance_paise': balancePaise,
        'savings_target_paise': savingsTargetPaise,
        'provider': provider,
      });

  Future<Map<String, dynamic>> whatIf(List<Txn> window, DateTime asOf,
          List<Map<String, Object?>> changes, {int? balancePaise, int savingsTargetPaise = 0}) =>
      _post('/v1/whatif', {
        'transactions': [for (final t in window) t.toApi()],
        'as_of': isoDate(asOf),
        'balance_paise': balancePaise,
        'savings_target_paise': savingsTargetPaise,
        'changes': changes,
      });

  void close() => _client.close();
}
