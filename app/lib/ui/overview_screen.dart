import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/money.dart';
import '../state/app_state.dart';
import 'theme.dart';

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final i = state.insights;
    final t = Theme.of(context).textTheme;
    final safe = i?['safe_to_spend'] as Map<String, dynamic>?;
    final forecast = i?['forecast'] as Map<String, dynamic>?;
    final anomalies = ((i?['anomalies'] as Map<String, dynamic>?)?['items'] as List?) ?? const [];

    return RefreshIndicator(
      onRefresh: state.refresh,
      child: ListView(padding: const EdgeInsets.all(16), children: [
        if (i == null)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                state.server.isComplete
                    ? 'Pull down to compute your insights.'
                    : 'Connect to the FinSight server in Settings to see safe-to-spend and forecasts. '
                        'Transactions and categories of known merchants work without it.',
                style: t.bodyMedium,
              ),
            ),
          ),
        if (safe != null) _SafeCard(safe: safe),
        if (safe == null && i != null)
          Card(
            child: ListTile(
              leading: const Icon(Icons.account_balance_wallet_outlined),
              title: const Text('Add your balance for safe-to-spend'),
              subtitle: const Text('No bank SMS with an available balance yet. Enter it in Settings.'),
            ),
          ),
        if (forecast != null) ...[
          const SizedBox(height: 12),
          _ForecastCard(forecast: forecast),
          const SizedBox(height: 12),
          _CategoriesCard(rows: (forecast['spent_by_category'] as List).cast<Map<String, dynamic>>()),
        ],
        if (anomalies.isNotEmpty) ...[
          const SizedBox(height: 12),
          Card(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                child: Text('Unusual payments', style: t.titleMedium),
              ),
              for (final a in anomalies.take(3).cast<Map<String, dynamic>>())
                ListTile(
                  leading: Icon(Icons.warning_amber_rounded, color: Theme.of(context).colorScheme.error),
                  title: Text(rupees(a['amount_paise'] as int)),
                  subtitle: Text(a['reason'] as String),
                ),
            ]),
          ),
        ],
        if (state.insightsAt != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text('Updated ${dayMonth(state.insightsAt!)}, ${timeOfDay(state.insightsAt!)}',
                textAlign: TextAlign.center, style: t.bodySmall),
          ),
      ]),
    );
  }
}

class _SafeCard extends StatelessWidget {
  const _SafeCard({required this.safe});
  final Map<String, dynamic> safe;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    final status = safe['status'] as String;
    final note = switch (status) {
      'at_risk' => 'At your current pace you would overshoot by '
          '${rupees(safe['projected_shortfall_paise'] as int? ?? 0)}.',
      'no_room' => 'Upcoming bills and your savings target use up your balance.',
      _ => 'On track for this month.',
    };
    return Card(
      color: scheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Safe to spend today', style: t.titleSmall?.copyWith(color: scheme.onPrimaryContainer)),
          const SizedBox(height: 4),
          Text(rupees(safe['safe_daily_paise'] as int),
              style: t.displaySmall?.copyWith(color: scheme.onPrimaryContainer, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(
            '${rupees(safe['safe_total_paise'] as int)} for the next ${safe['days_left']} days, after '
            '${rupees(safe['recurring_due_paise'] as int)} of upcoming bills and '
            '${rupees(safe['savings_target_paise'] as int)} of savings.',
            style: t.bodyMedium?.copyWith(color: scheme.onPrimaryContainer),
          ),
          const SizedBox(height: 8),
          Text(note, style: t.bodySmall?.copyWith(color: scheme.onPrimaryContainer)),
        ]),
      ),
    );
  }
}

class _ForecastCard extends StatelessWidget {
  const _ForecastCard({required this.forecast});
  final Map<String, dynamic> forecast;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final projected = forecast['projected_month_end_paise'] as int;
    final spent = forecast['spent_so_far_paise'] as int;
    final fraction = projected == 0 ? 0.0 : (spent / projected).clamp(0.0, 1.0);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('This month', style: t.titleMedium),
          const SizedBox(height: 8),
          Text('${rupees(spent)} spent so far, about ${rupees(projected)} by month end',
              style: t.bodyLarge),
          const SizedBox(height: 8),
          LinearProgressIndicator(value: fraction, minHeight: 8, borderRadius: BorderRadius.circular(4)),
          const SizedBox(height: 8),
          Text(
            'Give or take ${rupees(forecast['error_band_paise'] as int)}. '
            '${rupees(forecast['variable_daily_paise'] as int)} a day on day-to-day spending, '
            'plus ${rupees(forecast['recurring_due_paise'] as int)} of recurring payments still due.',
            style: t.bodySmall,
          ),
        ]),
      ),
    );
  }
}

class _CategoriesCard extends StatelessWidget {
  const _CategoriesCard({required this.rows});
  final List<Map<String, dynamic>> rows;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final t = Theme.of(context).textTheme;
    final spend = rows.where((r) => (r['spent_paise'] as int) > 0).toList();
    if (spend.isEmpty) return const SizedBox.shrink();
    final top = spend.first['spent_paise'] as int;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Where it went', style: t.titleMedium),
          const SizedBox(height: 12),
          for (final r in spend.take(6))
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(children: [
                Icon(iconFor(r['category'] as String), size: 20, color: colorFor(r['category'] as String)),
                const SizedBox(width: 8),
                SizedBox(width: 110, child: Text(state.rules.categoryName(r['category'] as String))),
                Expanded(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: (r['spent_paise'] as int) / top,
                      minHeight: 10,
                      color: colorFor(r['category'] as String),
                      backgroundColor: Colors.transparent,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(
                  width: 72,
                  child: Text(rupees(r['spent_paise'] as int), textAlign: TextAlign.end),
                ),
              ]),
            ),
        ]),
      ),
    );
  }
}
