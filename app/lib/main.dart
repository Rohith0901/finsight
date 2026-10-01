import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'core/rules.dart';
import 'data/database.dart';
import 'data/repository.dart';
import 'ingestion/normalizer.dart';
import 'ingestion/pipeline.dart';
import 'ingestion/sms_parser.dart';
import 'ingestion/sms_source.dart';
import 'services/masked_export.dart';
import 'state/app_state.dart';
import 'ui/consent_screen.dart';
import 'ui/home_shell.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final secrets = Secrets();
  final (db, wasReset) = await openOrResetEncryptedDatabase(secrets);
  final rules = SharedRules.fromJson(
    merchantsJson: await rootBundle.loadString('assets/shared/merchants.json'),
    hintsJson: await rootBundle.loadString('assets/shared/sms_hints.json'),
    categoriesJson: await rootBundle.loadString('assets/shared/categories.json'),
  );
  final parser = SmsParser(rules.hints);
  final normalizer = Normalizer(rules, await secrets.personSalt());
  final repo = Repository(db);
  final inbox = InboxSmsSource();
  final state = AppState(
    repo: repo,
    pipeline: IngestionPipeline(repo, parser, normalizer),
    rules: rules,
    inbox: inbox,
    demoJsonl: loadDemoAsset,
  );
  await state.load();
  if (wasReset) {
    state.status = 'Your saved data could not be unlocked on this phone, so FinSight started fresh.';
  }

  Future<String> export() async {
    final (file, count) = await exportMasked(inbox, parser, normalizer);
    return '$count rows written to ${file.path}';
  }

  runApp(ChangeNotifierProvider.value(value: state, child: FinSightApp(onExport: export)));
}

class FinSightApp extends StatelessWidget {
  const FinSightApp({super.key, this.onExport});
  final Future<String> Function()? onExport;

  @override
  Widget build(BuildContext context) {
    final consented = context.select<AppState, bool>((s) => s.consented);
    return MaterialApp(
      title: 'FinSight',
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      home: consented ? HomeShell(onExport: onExport) : const ConsentScreen(),
    );
  }
}
