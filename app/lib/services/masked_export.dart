// Developer export for building the real test set (ml/data/README.md).
// Debug builds only. Re-reads the inbox, masks identifying details, and writes
// one JSON line per bank transaction to the app's external files folder.

import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../ingestion/normalizer.dart';
import '../ingestion/pipeline.dart';
import '../ingestion/sms_parser.dart';
import '../ingestion/sms_source.dart';

final _longDigits = RegExp(r'[0-9]{9,}');
// Covers "A/c XX1234", "A/c ..1234", "Acct no: 1234", "card ending with 1234".
final _maskedAccount = RegExp(
    r'((?:(?:a/c|acct|account|\bac|card)\.?\s*(?:no\.?|number)?\s*(?:ending(?:\s*with)?)?|\bending(?:\s*with)?)'
    r'\s*[:\-]?\s*(?:[x*]+|\.\.)?\s*)([0-9]{3,6})',
    caseSensitive: false);
final _vpa = RegExp(r'[A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+');

String maskBody(String body, ParsedSms p, Normalizer n) {
  var out = body
      .replaceAllMapped(_longDigits, (m) => '9' * m.group(0)!.length)
      .replaceAllMapped(_maskedAccount, (m) => '${m.group(1)}${'0' * m.group(2)!.length}');
  out = out.replaceAllMapped(_vpa, (m) {
    final name = n.resolve(m.group(0));
    return name.kind == 'person' ? 'person@upi' : m.group(0)!;
  });
  final raw = p.merchantRaw;
  if (raw != null && !raw.contains('@') && n.resolve(raw, p2a: p.p2a, p2m: p.p2m).kind == 'person') {
    out = out.replaceAll(raw, 'PERSON NAME');
  }
  return out;
}

Future<(File, int)> exportMasked(InboxSmsSource inbox, SmsParser parser, Normalizer n) async {
  final dir = await getExternalStorageDirectory() ?? await getApplicationDocumentsDirectory();
  final file = File('${dir.path}/finsight_export_${DateTime.now().millisecondsSinceEpoch}.jsonl');
  final sink = file.openWrite();
  var count = 0;
  for (final m in await inbox.since(0)) {
    final p = parser.parse(m.sender, m.body);
    if (p.outcome != Outcome.transaction) continue;
    final name = n.resolve(p.merchantRaw, p2a: p.p2a, p2m: p.p2m);
    sink.writeln(jsonEncode({
      'merchant_norm': name.kind == 'person' ? '' : name.key,
      'descriptor': IngestionPipeline.descriptorFor(p, name),
      'mode': p.mode,
      'direction': p.direction,
      'amount_paise': p.amountPaise,
      'category': '',
      'masked_sms': maskBody(m.body, p, n),
      'sender': m.sender,
    }));
    count++;
  }
  await sink.close();
  return (file, count);
}
