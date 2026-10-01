// Plain data classes for rows the UI and the API client use.

class Txn {
  Txn({
    required this.id,
    required this.ts,
    required this.amountPaise,
    required this.direction,
    required this.merchantNorm,
    required this.merchantKey,
    required this.displayName,
    required this.merchantKind,
    required this.mode,
    required this.descriptor,
    required this.categorySource,
    required this.isSelfTransfer,
    required this.isRefund,
    this.merchantRaw,
    this.accountAlias,
    this.categoryId,
    this.confidence,
    this.source = 'sms',
  });

  final int id;
  final DateTime ts;
  final int amountPaise;
  final String direction;
  final String? merchantRaw;
  final String merchantNorm;
  final String merchantKey;
  final String displayName;
  final String merchantKind;
  final String? accountAlias;
  final String mode;
  final String descriptor;
  final String? categoryId;
  final String categorySource;
  final double? confidence;
  final bool isSelfTransfer;
  final bool isRefund;
  final String source;

  bool get isDebit => direction == 'debit';

  factory Txn.fromRow(Map<String, Object?> r) => Txn(
        id: r['id'] as int,
        ts: DateTime.fromMillisecondsSinceEpoch(r['ts'] as int),
        amountPaise: r['amount_paise'] as int,
        direction: r['direction'] as String,
        merchantRaw: r['merchant_raw'] as String?,
        merchantNorm: r['merchant_norm'] as String,
        merchantKey: r['merchant_key'] as String,
        displayName: r['display_name'] as String,
        merchantKind: r['merchant_kind'] as String,
        accountAlias: r['account_alias'] as String?,
        mode: r['mode'] as String,
        descriptor: r['descriptor'] as String,
        categoryId: r['category_id'] as String?,
        categorySource: r['category_source'] as String,
        confidence: (r['confidence'] as num?)?.toDouble(),
        isSelfTransfer: (r['is_self_transfer'] as int) == 1,
        isRefund: (r['is_refund'] as int) == 1,
        source: r['source'] as String,
      );

  /// The shape the backend accepts. No raw SMS, no reference, no account
  /// number, no payee name: only the parsed fields listed in docs/api.md.
  Map<String, Object?> toApi() => {
        'id': '$id',
        'ts': ts.toUtc().toIso8601String(),
        'amount_paise': amountPaise,
        'direction': direction,
        'merchant_norm': merchantNorm,
        'category': categoryId == null || categorySource == 'pending' ? null : categoryId,
        'account_alias': accountAlias,
        'mode': mode,
        'is_self_transfer': isSelfTransfer,
        'is_refund': isRefund,
      };
}
