// Encrypted local database (SQLCipher through sqflite_sqlcipher).
//
// The key is 32 random bytes made on first run and kept in the Android Keystore
// via flutter_secure_storage. Uninstalling the app destroys the key, and the
// data becomes unreadable. Tests open the same schema in memory without a key.

import 'dart:convert';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common/sqlite_api.dart';
import 'package:sqflite_sqlcipher/sqflite.dart' as cipher;

const schemaVersion = 1;

const _schemaV1 = [
  '''CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    ts INTEGER NOT NULL,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
    merchant_raw TEXT,
    merchant_norm TEXT NOT NULL DEFAULT '',
    merchant_key TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    merchant_kind TEXT NOT NULL DEFAULT 'unknown',
    account_alias TEXT,
    mode TEXT NOT NULL DEFAULT 'other',
    ref_no TEXT,
    descriptor TEXT NOT NULL DEFAULT '',
    category_id TEXT,
    category_source TEXT NOT NULL DEFAULT 'pending',
    confidence REAL,
    is_self_transfer INTEGER NOT NULL DEFAULT 0,
    is_refund INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'sms',
    parse_version INTEGER NOT NULL DEFAULT 1
  )''',
  'CREATE INDEX idx_txn_ts ON transactions (ts)',
  'CREATE INDEX idx_txn_pending ON transactions (category_source)',
  '''CREATE TABLE accounts (
    alias TEXT PRIMARY KEY,
    mask TEXT NOT NULL,
    bank TEXT,
    kind TEXT NOT NULL,
    last_balance_paise INTEGER,
    balance_ts INTEGER,
    UNIQUE (mask, kind)
  )''',
  '''CREATE TABLE category_overrides (
    merchant_key TEXT PRIMARY KEY,
    category_id TEXT NOT NULL,
    updated_at INTEGER NOT NULL
  )''',
  '''CREATE TABLE corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_id INTEGER NOT NULL,
    predicted TEXT,
    corrected TEXT NOT NULL,
    ts INTEGER NOT NULL
  )''',
  '''CREATE TABLE budgets (
    category_id TEXT NOT NULL,
    month TEXT NOT NULL,
    limit_paise INTEGER NOT NULL,
    PRIMARY KEY (category_id, month)
  )''',
  '''CREATE TABLE insights_cache (
    kind TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    computed_at INTEGER NOT NULL
  )''',
  '''CREATE TABLE review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    reason TEXT NOT NULL,
    ts INTEGER NOT NULL
  )''',
  'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
];

/// Migrations by target version. Add `2: [...]` here when the schema changes,
/// and bump [schemaVersion].
const migrations = <int, List<String>>{1: _schemaV1};

Future<void> onCreate(Database db, int version) async {
  for (var v = 1; v <= version; v++) {
    for (final sql in migrations[v] ?? const <String>[]) {
      await db.execute(sql);
    }
  }
}

Future<void> onUpgrade(Database db, int from, int to) async {
  for (var v = from + 1; v <= to; v++) {
    for (final sql in migrations[v] ?? const <String>[]) {
      await db.execute(sql);
    }
  }
}

const _keyName = 'finsight_db_key';
const _saltName = 'finsight_person_salt';

String _randomSecret() {
  final r = Random.secure();
  return base64UrlEncode(List<int>.generate(32, (_) => r.nextInt(256)));
}

/// Secrets kept in the Android Keystore.
class Secrets {
  Secrets([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();
  final FlutterSecureStorage _storage;

  Future<String> _getOrCreate(String name) async {
    final existing = await _storage.read(key: name);
    if (existing != null) return existing;
    final fresh = _randomSecret();
    await _storage.write(key: name, value: fresh);
    return fresh;
  }

  Future<String> databaseKey() => _getOrCreate(_keyName);
  Future<String> personSalt() => _getOrCreate(_saltName);
  Future<void> wipe() => _storage.deleteAll();
}

Future<Database> openEncryptedDatabase(String key) async {
  final dir = await cipher.getDatabasesPath();
  return cipher.openDatabase(
    p.join(dir, 'finsight.db'),
    password: key,
    version: schemaVersion,
    onCreate: onCreate,
    onUpgrade: onUpgrade,
  );
}

/// Opens the database, or starts a fresh one if the stored key can no longer
/// open it (the Keystore entry was lost or reset while the file survived).
/// The old file is unreadable without its key either way. Returns whether the
/// local data was reset, so the app can say so.
Future<(Database, bool)> openOrResetEncryptedDatabase(Secrets secrets) async {
  try {
    return (await openEncryptedDatabase(await secrets.databaseKey()), false);
  } on DatabaseException {
    await deleteEncryptedDatabase();
    await secrets.wipe();
    return (await openEncryptedDatabase(await secrets.databaseKey()), true);
  }
}

Future<void> deleteEncryptedDatabase() async {
  final dir = await cipher.getDatabasesPath();
  await cipher.deleteDatabase(p.join(dir, 'finsight.db'));
}
