// SMS -> transaction row. The body is parsed in memory and never written down.
//
// Category resolution order (ADR-006): self transfer, then the user's override
// for this merchant, then rules (people are Transfers, known brands map to
// their category, salary is Income), and only then the backend model.

import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../data/repository.dart';
import 'normalizer.dart';
import 'sender_filter.dart';
import 'sms_parser.dart';
import 'sms_source.dart';

enum IngestStatus { inserted, duplicate, skipped, rejected, balance, miss }

class IngestionPipeline {
  IngestionPipeline(this.repo, this.parser, this.normalizer);

  final Repository repo;
  final SmsParser parser;
  final Normalizer normalizer;

  static String _sha(String s) => sha256.convert(utf8.encode(s)).toString();

  static String descriptorFor(ParsedSms p, MerchantName name) {
    final tokens = <String>{...p.hints};
    if (p.card != null) tokens.add('${p.card}_card');
    if (p.p2m) tokens.add('p2m');
    if (p.p2a) tokens.add('p2a');
    if (name.kind == 'qr') tokens.add('qr');
    return (tokens.toList()..sort()).join(' ');
  }

  /// Override key: the merchant key, or the raw UPI handle for anonymous QR
  /// payments, so labelling one payment to a tea stall's QR labels the rest.
  static String merchantKeyFor(ParsedSms p, MerchantName name) {
    if (name.key.isNotEmpty) return name.key;
    final raw = (p.merchantRaw ?? '').toLowerCase();
    return raw.contains('@') ? 'vpa:$raw' : '';
  }

  Future<IngestStatus> ingest(SmsMessage m, {String source = 'sms'}) async {
    final p = parser.parse(m.sender, m.body);
    final ts = m.receivedAt.millisecondsSinceEpoch;
    switch (p.outcome) {
      case Outcome.skipped:
        return IngestStatus.skipped;
      case Outcome.rejected:
        return IngestStatus.rejected;
      case Outcome.balance:
        await repo.updateBalanceByMask(p.accountMask!, p.balancePaise!, ts);
        return IngestStatus.balance;
      case Outcome.miss:
        final s = p.sender;
        if (s != null && s.kind == SenderKind.bank && completedVerb.hasMatch(m.body)) {
          await repo.addReview(m.sender, p.reason, ts);
        }
        return IngestStatus.miss;
      case Outcome.transaction:
        break;
    }

    final kind = p.card == 'credit' ? 'credit_card' : (p.card == 'debit' ? 'debit_card' : 'savings');
    final alias = p.accountMask == null
        ? null
        : await repo.accountFor(p.accountMask!, p.sender?.bank, kind);
    final name = normalizer.resolve(p.merchantRaw, p2a: p.p2a, p2m: p.p2m);
    final key = merchantKeyFor(p, name);
    final selfTransfer =
        p.isCardBill || (p.merchantRaw != null && normalizer.isCardBillName(p.merchantRaw!));

    // Duplicates: same bank reference, or the same payment within a minute.
    final String fingerprint;
    if (p.refNo != null) {
      fingerprint = _sha('ref|${p.refNo}|${p.direction}|${p.amountPaise}');
    } else {
      final minute = ts ~/ 60000;
      String fp(int bucket) =>
          _sha('$alias|${p.amountPaise}|${name.key}|${p.direction}|$bucket');
      for (final b in [minute - 1, minute + 1]) {
        if (await repo.hasFingerprint(fp(b))) return IngestStatus.duplicate;
      }
      fingerprint = fp(minute);
    }
    if (await repo.hasFingerprint(fingerprint)) return IngestStatus.duplicate;

    String? category;
    var categorySource = 'pending';
    final override = await repo.overrideFor(key);
    if (selfTransfer) {
      category = 'transfers';
      categorySource = 'rule';
    } else if (override != null) {
      category = override;
      categorySource = 'override';
    } else if (name.kind == 'person') {
      category = 'transfers';
      categorySource = 'rule';
    } else if (name.kind == 'known') {
      category = name.category;
      categorySource = 'rule';
    } else if (p.direction == 'credit' &&
        (p.hints.contains('salary') || p.hints.contains('interest') ||
            p.hints.contains('cashback'))) {
      category = 'income';
      categorySource = 'rule';
    }

    final id = await repo.insertTransaction({
      'fingerprint': fingerprint,
      'ts': ts,
      'amount_paise': p.amountPaise,
      'direction': p.direction,
      'merchant_raw': p.merchantRaw,
      'merchant_norm': name.key,
      'merchant_key': key,
      'display_name': name.display,
      'merchant_kind': name.kind,
      'account_alias': alias,
      'mode': p.mode,
      'ref_no': p.refNo,
      'descriptor': descriptorFor(p, name),
      'category_id': category,
      'category_source': categorySource,
      'is_self_transfer': selfTransfer ? 1 : 0,
      'is_refund': p.isRefund ? 1 : 0,
      'source': source,
    });
    if (id == 0) return IngestStatus.duplicate;
    if (alias != null && p.balancePaise != null && kind != 'credit_card') {
      await repo.updateBalance(alias, p.balancePaise!, ts);
    }
    if (!selfTransfer) await repo.linkSelfTransfer(id);
    return IngestStatus.inserted;
  }

  /// Reads everything since the last checkpoint. Safe to run any number of
  /// times: duplicates are recognised and skipped.
  Future<Map<IngestStatus, int>> syncFrom(SmsSource source, {String tag = 'sms'}) async {
    final checkpointKey = 'checkpoint_$tag';
    final since = int.tryParse(await repo.setting(checkpointKey) ?? '') ?? 0;
    final messages = await source.since(since)
      ..sort((a, b) => a.receivedAt.compareTo(b.receivedAt));
    final counts = {for (final s in IngestStatus.values) s: 0};
    var latest = since;
    for (final m in messages) {
      IngestStatus status;
      try {
        status = await ingest(m, source: tag);
      } catch (_) {
        // e.g. an amount too large to parse. Count it and move on, so the
        // checkpoint still advances past it.
        status = IngestStatus.miss;
      }
      counts[status] = counts[status]! + 1;
      final t = m.receivedAt.millisecondsSinceEpoch;
      if (t > latest) latest = t;
    }
    await repo.setSetting(checkpointKey, '$latest');
    return counts;
  }
}
