// Smoke test for the first screen. This file also stops `flutter create .`
// from adding its counter-app sample test, which would not compile here.

import 'package:finsight/data/repository.dart';
import 'package:finsight/ingestion/normalizer.dart';
import 'package:finsight/ingestion/pipeline.dart';
import 'package:finsight/ingestion/sms_parser.dart';
import 'package:finsight/main.dart';
import 'package:finsight/state/app_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'support.dart';

void main() {
  late AppState state;

  setUpAll(() async {
    final rules = loadRules();
    final repo = Repository(await openTestDb());
    state = AppState(
      repo: repo,
      pipeline: IngestionPipeline(repo, SmsParser(rules.hints), Normalizer(rules, 'test')),
      rules: rules,
    );
  });

  testWidgets('a new install opens on the consent screen', (tester) async {
    await tester.pumpWidget(ChangeNotifierProvider.value(value: state, child: const FinSightApp()));
    expect(find.text('FinSight'), findsOneWidget);
    expect(find.text('The message text never leaves your phone'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Allow reading bank SMS'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Try with demo data instead'), findsOneWidget);
  });
}
