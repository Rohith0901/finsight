// All database access, in plain SQL.

import 'dart:convert';
import 'dart:math';

import 'package:sqflite_common/sqlite_api.dart';

import 'models.dart';

class Repository {
  Repository(this.db);
  final Database db;
  final _rng = Random.secure();

  int get _now => DateTime.now().millisecondsSinceEpoch;

  // ------------------------------------------------------------ settings

  Future<String?> setting(String key) async {
    final rows = await db.query('settings', where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : rows.first['value'] as String;
  }

  Future<void> setSetting(String key, String? value) async {
    if (value == null) {
      await db.delete('settings', where: 'key = ?', whereArgs: [key]);
    } else {
      await db.insert('settings', {'key': key, 'value': value},
          conflictAlgorithm: ConflictAlgorithm.replace);
    }
  }

  // ------------------------------------------------------------ accounts

  Future<String> accountFor(String mask, String? bank, String kind) async {
    final rows = await db.query('accounts',
        where: 'mask = ? AND kind = ?', whereArgs: [mask, kind], limit: 1);
    if (rows.isNotEmpty) return rows.first['alias'] as String;
    final alias = 'acc_${_rng.nextInt(1 << 32).toRadixString(16).padLeft(8, '0')}';
    await db.insert('accounts', {'alias': alias, 'mask': mask, 'bank': bank, 'kind': kind});
    return alias;
  }

  Future<void> updateBalance(String alias, int balancePaise, int ts) async {
    await db.update('accounts', {'last_balance_paise': balancePaise, 'balance_ts': ts},
        where: 'alias = ? AND (balance_ts IS NULL OR balance_ts <= ?)', whereArgs: [alias, ts]);
  }

  Future<void> updateBalanceByMask(String mask, int balancePaise, int ts) async {
    final rows = await db.query('accounts',
        where: "mask = ? AND kind != 'credit_card'", whereArgs: [mask], limit: 1);
    final alias = rows.isEmpty
        ? await accountFor(mask, null, 'savings')
        : rows.first['alias'] as String;
    await updateBalance(alias, balancePaise, ts);
  }

  /// Sum of the latest known balances of savings accounts. Debit-card balances
  /// are only used when no savings balance is known (they describe the same
  /// account; see docs/tech-debt.md).
  Future<int?> knownBalance() async {
    final savings = await db.rawQuery(
        'SELECT SUM(last_balance_paise) AS s, COUNT(last_balance_paise) AS n FROM accounts '
        "WHERE kind = 'savings' AND last_balance_paise IS NOT NULL");
    if ((savings.first['n'] as int) > 0) return savings.first['s'] as int;
    final debit = await db.rawQuery(
        "SELECT last_balance_paise AS b FROM accounts WHERE kind = 'debit_card' "
        'AND last_balance_paise IS NOT NULL ORDER BY balance_ts DESC LIMIT 1');
    return debit.isEmpty ? null : debit.first['b'] as int;
  }

  // ------------------------------------------------------------ transactions

  Future<bool> hasFingerprint(String fp) async =>
      (await db.query('transactions', columns: ['id'], where: 'fingerprint = ?',
              whereArgs: [fp], limit: 1))
          .isNotEmpty;

  Future<int> insertTransaction(Map<String, Object?> row) =>
      db.insert('transactions', row, conflictAlgorithm: ConflictAlgorithm.ignore);

  Future<List<Txn>> recent({int limit = 300}) async {
    final rows = await db.query('transactions', orderBy: 'ts DESC', limit: limit);
    return rows.map(Txn.fromRow).toList();
  }

  Future<List<Txn>> since(DateTime from) async {
    final rows = await db.query('transactions',
        where: 'ts >= ?', whereArgs: [from.millisecondsSinceEpoch], orderBy: 'ts ASC');
    return rows.map(Txn.fromRow).toList();
  }

  Future<List<Txn>> pending({int limit = 500}) async {
    final rows = await db.query('transactions',
        where: "category_source = 'pending'", orderBy: 'ts DESC', limit: limit);
    return rows.map(Txn.fromRow).toList();
  }

  Future<void> setCategory(int id, String? category, String source, double? confidence) =>
      db.update('transactions',
          {'category_id': category, 'category_source': source, 'confidence': confidence},
          where: 'id = ?', whereArgs: [id]);

  /// Pairs an outgoing payment with an incoming one of the same amount on a
  /// different own account within 30 minutes: money moved between your own
  /// accounts, so neither side is spending or income.
  Future<void> linkSelfTransfer(int id) async {
    final rows = await db.query('transactions', where: 'id = ?', whereArgs: [id]);
    if (rows.isEmpty) return;
    final t = rows.first;
    // Own-account moves show your own name or no merchant at all. When both
    // sides name a person it must be the same person (you), so paying one
    // friend and being repaid by another isn't mistaken for a self transfer.
    if (!['person', 'unknown'].contains(t['merchant_kind'])) return;
    const window = 30 * 60 * 1000;
    final other = await db.query('transactions',
        where: 'id != ? AND amount_paise = ? AND direction != ? AND account_alias IS NOT NULL '
            'AND account_alias != ? AND ts BETWEEN ? AND ? AND is_self_transfer = 0 '
            "AND merchant_kind IN ('person', 'unknown') "
            "AND (merchant_kind = 'unknown' OR ? = 'unknown' OR merchant_norm = ?)",
        whereArgs: [
          id, t['amount_paise'], t['direction'], t['account_alias'] ?? '',
          (t['ts'] as int) - window, (t['ts'] as int) + window,
          t['merchant_kind'], t['merchant_norm'],
        ],
        limit: 1);
    if (other.isEmpty || t['account_alias'] == null) return;
    for (final x in [id, other.first['id']]) {
      await db.update('transactions',
          {'is_self_transfer': 1, 'category_id': 'transfers', 'category_source': 'rule'},
          where: 'id = ?', whereArgs: [x]);
    }
  }

  // ------------------------------------------------------------ corrections

  Future<String?> overrideFor(String merchantKey) async {
    if (merchantKey.isEmpty) return null;
    final rows = await db.query('category_overrides',
        where: 'merchant_key = ?', whereArgs: [merchantKey], limit: 1);
    return rows.isEmpty ? null : rows.first['category_id'] as String;
  }

  /// The user's correction: fix this row, remember it for the merchant, apply it
  /// to that merchant's other rows, and log it for the next retraining.
  Future<void> correct(Txn t, String category) async {
    await db.transaction((tx) async {
      await tx.insert('corrections', {
        'txn_id': t.id, 'predicted': t.categoryId, 'corrected': category, 'ts': _now,
      });
      await tx.update('transactions', {'category_id': category, 'category_source': 'user'},
          where: 'id = ?', whereArgs: [t.id]);
      if (t.merchantKey.isNotEmpty) {
        await tx.insert('category_overrides',
            {'merchant_key': t.merchantKey, 'category_id': category, 'updated_at': _now},
            conflictAlgorithm: ConflictAlgorithm.replace);
        await tx.update('transactions', {'category_id': category, 'category_source': 'override'},
            where: "merchant_key = ? AND category_source != 'user'", whereArgs: [t.merchantKey]);
      }
    });
  }

  // ------------------------------------------------------------ cache, review

  Future<void> cache(String kind, Object payload) => db.insert('insights_cache',
      {'kind': kind, 'payload': jsonEncode(payload), 'computed_at': _now},
      conflictAlgorithm: ConflictAlgorithm.replace);

  Future<(Map<String, dynamic>, DateTime)?> cached(String kind) async {
    final rows = await db.query('insights_cache', where: 'kind = ?', whereArgs: [kind]);
    if (rows.isEmpty) return null;
    return (
      jsonDecode(rows.first['payload'] as String) as Map<String, dynamic>,
      DateTime.fromMillisecondsSinceEpoch(rows.first['computed_at'] as int),
    );
  }

  /// A message that looked like a transaction but no pattern understood. Only
  /// the sender and the reason are kept, never the text.
  Future<void> addReview(String sender, String reason, int ts) =>
      db.insert('review', {'sender': sender, 'reason': reason, 'ts': ts});

  Future<List<Map<String, Object?>>> reviewItems() =>
      db.query('review', orderBy: 'ts DESC', limit: 100);

  Future<void> wipe() async {
    for (final table in ['transactions', 'accounts', 'category_overrides', 'corrections',
      'budgets', 'insights_cache', 'review', 'settings']) {
      await db.delete(table);
    }
  }
}
