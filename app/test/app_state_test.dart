import 'package:finsight/data/repository.dart';
import 'package:finsight/ingestion/normalizer.dart';
import 'package:finsight/ingestion/pipeline.dart';
import 'package:finsight/ingestion/sms_parser.dart';
import 'package:finsight/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  test('a test message is recorded like a real SMS and the balance drops by the amount', () async {
    final rules = loadRules();
    final repo = Repository(await openTestDb());
    final state = AppState(
      repo: repo,
      pipeline: IngestionPipeline(repo, SmsParser(rules.hints), Normalizer(rules, 'test')),
      rules: rules,
    );

    // The bank reports a balance first, so the app knows account 4821.
    expect(
      await state.simulateSms('VM-HDFCBK',
          'Available balance in your A/c XX4821 is Rs 10,000.00 as on 01-10-26. -HDFC Bank'),
      startsWith('Balance update only'),
    );

    final samples = await state.sampleMessages();
    final upi = samples.first;
    expect(upi.$3, contains('**4821'));

    final result = await state.simulateSms(upi.$2, upi.$3);
    expect(result, contains('Debited ₹250.00: Swiggy, Food.'));
    expect(result, contains('Balance ₹10,000 → ₹9,750.'));

    // The same message again is recognised as a duplicate.
    expect(await state.simulateSms(upi.$2, upi.$3), startsWith('Already recorded'));

    // Remarks after a payee are cut off, so the person is recognised.
    final person = samples[3];
    expect(await state.simulateSms(person.$2, person.$3), contains('J Jothimani, Transfers.'));

    // OTPs are ignored.
    final otp = samples.last;
    expect(await state.simulateSms(otp.$2, otp.$3), contains('one-time password'));
  });
}
