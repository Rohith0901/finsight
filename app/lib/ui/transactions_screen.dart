import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/money.dart';
import '../data/models.dart';
import '../state/app_state.dart';
import 'theme.dart';

class TransactionsScreen extends StatelessWidget {
  const TransactionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final txns = state.transactions;
    if (txns.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(
            state.hasSmsPermission
                ? 'No bank transactions yet. Pull down on Overview after your next payment.'
                : 'No transactions yet. Allow SMS access or load demo data in Settings.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    final items = <Widget>[];
    DateTime? day;
    for (final t in txns) {
      final d = DateTime(t.ts.year, t.ts.month, t.ts.day);
      if (day == null || d != day) {
        day = d;
        items.add(Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text(dayMonth(d), style: Theme.of(context).textTheme.labelLarge),
        ));
      }
      items.add(TransactionTile(txn: t));
    }
    return RefreshIndicator(
      onRefresh: () => state.scanInbox(),
      child: ListView(children: items),
    );
  }
}

class TransactionTile extends StatelessWidget {
  const TransactionTile({super.key, required this.txn});
  final Txn txn;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final scheme = Theme.of(context).colorScheme;
    final category = txn.categorySource == 'pending' ? null : txn.categoryId;
    final label = txn.categorySource == 'pending'
        ? 'Waiting for a category'
        : state.rules.categoryName(category) +
            (txn.categorySource == 'model' && txn.confidence != null
                ? ' · ${(txn.confidence! * 100).round()}% sure'
                : '');
    final amount = '${txn.isDebit ? '-' : '+'}${rupees(txn.amountPaise, decimals: true)}';
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: colorFor(category).withValues(alpha: 0.18),
        child: Icon(iconFor(category), color: colorFor(category)),
      ),
      title: Text(txn.displayName.isEmpty ? 'Unknown' : txn.displayName,
          maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(txn.isSelfTransfer ? 'Between your own accounts' : label),
      trailing: Text(amount,
          style: TextStyle(
            fontWeight: FontWeight.w600,
            color: txn.isDebit ? scheme.onSurface : Colors.green.shade700,
          )),
      onTap: () => showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (_) => ChangeNotifierProvider.value(value: state, child: _CategorySheet(txn: txn)),
      ),
    );
  }
}

class _CategorySheet extends StatelessWidget {
  const _CategorySheet({required this.txn});
  final Txn txn;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final t = Theme.of(context).textTheme;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(txn.displayName, style: t.titleMedium),
          Text('${rupees(txn.amountPaise, decimals: true)} · ${dayMonth(txn.ts)} ${timeOfDay(txn.ts)} · '
              '${txn.mode.toUpperCase()}'),
          const SizedBox(height: 12),
          Text(
            txn.merchantKey.isEmpty
                ? 'Choose a category for this payment.'
                : 'Choose a category. FinSight will use it for every payment to this merchant.',
            style: t.bodySmall,
          ),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final c in state.rules.categories)
              ChoiceChip(
                avatar: Icon(iconFor(c.id), size: 18, color: colorFor(c.id)),
                label: Text(c.name),
                selected: txn.categoryId == c.id,
                onSelected: (_) async {
                  await state.correct(txn, c.id);
                  if (context.mounted) Navigator.of(context).pop();
                },
              ),
          ]),
        ]),
      ),
    );
  }
}
