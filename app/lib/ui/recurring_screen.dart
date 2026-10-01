import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/money.dart';
import '../state/app_state.dart';
import 'theme.dart';

class RecurringScreen extends StatelessWidget {
  const RecurringScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final items = (((state.insights?['recurring'] as Map<String, dynamic>?)?['items'] as List?) ??
            const [])
        .cast<Map<String, dynamic>>();
    if (items.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text('No recurring payments found yet. It takes three regular payments to spot one.',
              textAlign: TextAlign.center),
        ),
      );
    }
    final monthly = items.fold<int>(0, (s, i) => s + (i['monthly_cost_paise'] as int));
    final names = {for (final t in state.transactions) t.merchantNorm: t.displayName};
    final sorted = [...items]..sort((a, b) => (a['next_due'] as String).compareTo(b['next_due'] as String));
    return ListView(padding: const EdgeInsets.symmetric(vertical: 8), children: [
      Padding(
        padding: const EdgeInsets.all(16),
        child: Text('${items.length} recurring payments, about ${rupees(monthly)} a month '
            '(${rupees(monthly * 12)} a year)',
            style: Theme.of(context).textTheme.titleMedium),
      ),
      for (final i in sorted)
        ListTile(
          leading: Icon(iconFor(i['category'] as String?), color: colorFor(i['category'] as String?)),
          title: Text(names[i['merchant_norm']] ?? i['merchant_norm'] as String),
          subtitle: Text('${i['period']} · next ${dayMonth(DateTime.parse(i['next_due'] as String))}'
              '${i['kind'] == 'bill' ? ' · amount varies' : ''}'),
          trailing: Text(rupees(i['median_amount_paise'] as int)),
        ),
    ]);
  }
}
