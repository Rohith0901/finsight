import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../core/money.dart';
import '../state/app_state.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, this.onExport});

  /// Debug-only masked export (lib/services/masked_export.dart); null hides it.
  final Future<String> Function()? onExport;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _url, _token, _fingerprint, _balance, _savings;

  @override
  void initState() {
    super.initState();
    final s = context.read<AppState>();
    _url = TextEditingController(text: s.server.baseUrl);
    _token = TextEditingController(text: s.server.token);
    _fingerprint = TextEditingController(text: s.server.fingerprint);
    _balance = TextEditingController(
        text: s.manualBalancePaise == null ? '' : '${s.manualBalancePaise! ~/ 100}');
    _savings = TextEditingController(text: '${s.savingsTargetPaise ~/ 100}');
  }

  @override
  void dispose() {
    for (final c in [_url, _token, _fingerprint, _balance, _savings]) {
      c.dispose();
    }
    super.dispose();
  }

  void _toast(String msg) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final t = Theme.of(context).textTheme;
    Widget heading(String s) =>
        Padding(padding: const EdgeInsets.fromLTRB(0, 24, 0, 8), child: Text(s, style: t.titleMedium));
    return ListView(padding: const EdgeInsets.all(16), children: [
      heading('Server'),
      TextField(
          controller: _url,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(labelText: 'Address', hintText: 'https://192.168.1.20:8443')),
      const SizedBox(height: 8),
      TextField(controller: _token, decoration: const InputDecoration(labelText: 'API token')),
      const SizedBox(height: 8),
      TextField(
          controller: _fingerprint,
          decoration: const InputDecoration(
              labelText: 'Certificate fingerprint (SHA-256)', helperText: 'Printed by scripts/gen_cert.sh')),
      const SizedBox(height: 8),
      Row(children: [
        FilledButton(
          onPressed: () async {
            await state.saveServer(
                ServerConfig(baseUrl: _url.text, token: _token.text, fingerprint: _fingerprint.text));
            final msg = await state.testConnection();
            if (mounted) _toast(msg);
          },
          child: const Text('Save and test'),
        ),
        const SizedBox(width: 8),
        OutlinedButton(onPressed: state.busy ? null : state.refresh, child: const Text('Update insights')),
      ]),
      heading('Money'),
      Text(state.smsBalancePaise == null
          ? 'No balance seen in bank SMS yet.'
          : 'Balance from your bank SMS: ${rupees(state.smsBalancePaise!)}'),
      const SizedBox(height: 8),
      TextField(
          controller: _balance,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
              labelText: 'Balance to use instead (₹, optional)', helperText: 'Leave empty to use the SMS balance')),
      const SizedBox(height: 8),
      TextField(
          controller: _savings,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Savings target this month (₹)')),
      const SizedBox(height: 8),
      FilledButton.tonal(
        onPressed: () async {
          const maxRupees = 1000000000; // the server accepts up to ₹1,000 crore
          final b = int.tryParse(_balance.text.trim());
          final target = int.tryParse(_savings.text.trim()) ?? 0;
          await state.saveMoney(
              manualBalance: b == null ? null : b.clamp(-maxRupees, maxRupees) * 100,
              savingsTarget: target.clamp(0, maxRupees) * 100);
          if (mounted) _toast('Saved');
        },
        child: const Text('Save'),
      ),
      heading('Assistant'),
      SegmentedButton<String>(
        segments: const [
          ButtonSegment(value: 'auto', label: Text('Server default')),
          ButtonSegment(value: 'ollama', label: Text('Local model')),
          ButtonSegment(value: 'none', label: Text('No model')),
        ],
        selected: {state.assistantProvider == 'gemini' ? 'auto' : state.assistantProvider},
        onSelectionChanged: (s) => state.setAssistantProvider(s.first),
      ),
      const SizedBox(height: 4),
      Text('The answer\'s numbers always come from your data. A model only changes the wording.',
          style: t.bodySmall),
      heading('Messages'),
      ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.sms_outlined),
        title: Text(state.hasSmsPermission ? 'SMS access allowed' : 'SMS access not allowed'),
        trailing: TextButton(
          onPressed: state.busy ? null : (state.hasSmsPermission ? state.scanInbox : state.giveConsent),
          child: Text(state.hasSmsPermission ? 'Scan now' : 'Allow'),
        ),
      ),
      ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.science_outlined),
        title: const Text('Load demo data'),
        subtitle: const Text('Three months of a sample user\'s bank messages'),
        onTap: state.busy ? null : state.loadDemo,
      ),
      FutureBuilder<List<Map<String, Object?>>>(
        future: state.repo.reviewItems(),
        builder: (context, snap) {
          final rows = snap.data ?? const [];
          return ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.rule),
            title: Text('Needs review: ${rows.length}'),
            subtitle: const Text('Bank messages no pattern understood (only the sender is kept)'),
            onTap: rows.isEmpty
                ? null
                : () => showDialog<void>(
                      context: context,
                      builder: (_) => AlertDialog(
                        title: const Text('Needs review'),
                        content: SizedBox(
                          width: double.maxFinite,
                          child: ListView(shrinkWrap: true, children: [
                            for (final r in rows)
                              ListTile(
                                title: Text(r['sender'] as String),
                                subtitle: Text('${r['reason']} · '
                                    '${dayMonth(DateTime.fromMillisecondsSinceEpoch(r['ts'] as int))}'),
                              ),
                          ]),
                        ),
                      ),
                    ),
          );
        },
      ),
      if (kDebugMode && widget.onExport != null)
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.file_download_outlined),
          title: const Text('Developer: export masked messages'),
          subtitle: const Text('For the real test set. Read the file before sharing it.'),
          onTap: () async {
            final msg = await widget.onExport!();
            if (mounted) _toast(msg);
          },
        ),
      heading('Privacy'),
      OutlinedButton.icon(
        style: OutlinedButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
        icon: const Icon(Icons.delete_forever),
        label: const Text('Delete all my data'),
        onPressed: state.busy ? null : () async {
          final ok = await showDialog<bool>(
            context: context,
            builder: (c) => AlertDialog(
              title: const Text('Delete everything?'),
              content: const Text('Every transaction, setting and correction on this phone is removed.'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
                FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Delete')),
              ],
            ),
          );
          if (ok == true) await state.deleteEverything();
        },
      ),
      const SizedBox(height: 24),
    ]);
  }
}
