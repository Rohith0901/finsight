import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

/// Processes a bank message picked or pasted here exactly as if it had just
/// arrived by SMS: same parser, rules and duplicate check. For demos and for
/// testing without touching the phone's real inbox.
class TestMessageScreen extends StatefulWidget {
  const TestMessageScreen({super.key});

  @override
  State<TestMessageScreen> createState() => _TestMessageScreenState();
}

class _TestMessageScreenState extends State<TestMessageScreen> {
  final _sender = TextEditingController();
  final _body = TextEditingController();
  List<(String, String, String)> _samples = const [];
  String? _result;
  bool _working = false;

  @override
  void initState() {
    super.initState();
    _loadSamples(fillFirst: true);
  }

  Future<void> _loadSamples({bool fillFirst = false}) async {
    final samples = await context.read<AppState>().sampleMessages();
    if (!mounted) return;
    setState(() {
      _samples = samples;
      if (fillFirst && samples.isNotEmpty) _use(samples.first);
    });
  }

  void _use((String, String, String) sample) {
    _sender.text = sample.$2;
    _body.text = sample.$3;
    _result = null;
  }

  Future<void> _process() async {
    setState(() => _working = true);
    final result = await context.read<AppState>().simulateSms(_sender.text, _body.text);
    if (!mounted) return;
    setState(() {
      _result = result;
      _working = false;
    });
    await _loadSamples(); // fresh references and balance for the next try
  }

  @override
  void dispose() {
    _sender.dispose();
    _body.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Test with a bank message')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text('The message goes through the same steps as a real SMS. Nothing is added to the '
            'phone\'s SMS inbox.', style: t.bodyMedium),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final s in _samples)
            ActionChip(label: Text(s.$1), onPressed: () => setState(() => _use(s))),
        ]),
        const SizedBox(height: 16),
        TextField(
          controller: _sender,
          decoration: const InputDecoration(labelText: 'Sender', border: OutlineInputBorder()),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _body,
          minLines: 4,
          maxLines: 8,
          decoration: const InputDecoration(labelText: 'Message', border: OutlineInputBorder()),
        ),
        const SizedBox(height: 12),
        FilledButton(
          onPressed: _working ? null : _process,
          child: const Text('Process as if it just arrived'),
        ),
        if (_result != null) ...[
          const SizedBox(height: 16),
          Card(
            child: Padding(padding: const EdgeInsets.all(16), child: Text(_result!, style: t.bodyLarge)),
          ),
        ],
      ]),
    );
  }
}
