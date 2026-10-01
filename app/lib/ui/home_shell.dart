import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import 'ask_screen.dart';
import 'overview_screen.dart';
import 'recurring_screen.dart';
import 'settings_screen.dart';
import 'transactions_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, this.onExport});
  final Future<String> Function()? onExport;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int _tab = 0;
  static const _titles = ['FinSight', 'Transactions', 'Recurring', 'Ask', 'Settings'];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      state.watchInbox();
      state.scanInbox(quiet: true);
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    // Catch up from the inbox whenever the app comes back to the foreground.
    if (s == AppLifecycleState.resumed) context.read<AppState>().scanInbox(quiet: true);
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final pages = [
      const OverviewScreen(),
      const TransactionsScreen(),
      const RecurringScreen(),
      const AskScreen(),
      SettingsScreen(onExport: widget.onExport),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_tab]),
        bottom: state.busy
            ? const PreferredSize(preferredSize: Size.fromHeight(2), child: LinearProgressIndicator())
            : null,
        actions: [
          if (state.status != null && !state.busy)
            IconButton(
              tooltip: state.status,
              icon: const Icon(Icons.info_outline),
              onPressed: () => ScaffoldMessenger.of(context)
                  .showSnackBar(SnackBar(content: Text(state.status!))),
            ),
        ],
      ),
      body: IndexedStack(index: _tab, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), label: 'Overview'),
          NavigationDestination(icon: Icon(Icons.receipt_long_outlined), label: 'Spending'),
          NavigationDestination(icon: Icon(Icons.autorenew), label: 'Recurring'),
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), label: 'Ask'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), label: 'Settings'),
        ],
      ),
    );
  }
}
