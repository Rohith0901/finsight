import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

/// Explains exactly what is read before Android asks for the SMS permission.
class ConsentScreen extends StatelessWidget {
  const ConsentScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final t = Theme.of(context).textTheme;
    Widget point(IconData icon, String title, String body) => Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 16),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: t.titleSmall),
                const SizedBox(height: 2),
                Text(body, style: t.bodyMedium),
              ]),
            ),
          ]),
        );
    return Scaffold(
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.all(24), children: [
          const SizedBox(height: 24),
          Text('FinSight', style: t.headlineMedium),
          const SizedBox(height: 8),
          Text('Your spending, from the bank messages you already get.', style: t.bodyLarge),
          const SizedBox(height: 32),
          point(Icons.sms_outlined, 'Reads bank messages only',
              'Messages from phone numbers are skipped before the app sees them. OTPs and offers are ignored.'),
          point(Icons.lock_outline, 'The message text never leaves your phone',
              'Only the amount, date, merchant and type are kept, in an encrypted database.'),
          point(Icons.cloud_off_outlined, 'The server stores nothing',
              'Insights are computed from what the phone sends with each request, then forgotten.'),
          point(Icons.delete_outline, 'Delete everything any time',
              'Settings > Delete all my data removes every record from this phone.'),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: state.busy ? null : () => state.giveConsent(),
            child: const Text('Allow reading bank SMS'),
          ),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: state.busy
                ? null
                : () async {
                    await state.repo.setSetting('consent_ts', DateTime.now().toIso8601String());
                    await state.load();
                    await state.loadDemo();
                  },
            child: const Text('Try with demo data instead'),
          ),
        ]),
      ),
    );
  }
}
