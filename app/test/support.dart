import 'dart:io';

import 'package:finsight/core/rules.dart';
import 'package:finsight/data/database.dart' as schema;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// `flutter test` runs from app/, so the shared contracts are one level up.
String sharedFile(String name) => File('../shared/$name').readAsStringSync();

SharedRules loadRules() => SharedRules.fromJson(
      merchantsJson: sharedFile('merchants.json'),
      hintsJson: sharedFile('sms_hints.json'),
      categoriesJson: sharedFile('categories.json'),
    );

Future<Database> openTestDb() async {
  sqfliteFfiInit();
  return databaseFactoryFfi.openDatabase(
    inMemoryDatabasePath,
    options: OpenDatabaseOptions(
      version: schema.schemaVersion,
      onCreate: schema.onCreate,
      onUpgrade: schema.onUpgrade,
      // Without this, every ':memory:' open returns the same database and
      // the tests see each other's rows.
      singleInstance: false,
    ),
  );
}
