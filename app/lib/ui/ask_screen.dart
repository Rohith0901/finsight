import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

class AskScreen extends StatefulWidget {
  const AskScreen({super.key});

  @override
  State<AskScreen> createState() => _AskScreenState();
}

class _AskScreenState extends State<AskScreen> {
  final _controller = TextEditingController();
  static const _examples = [
    'Why did I overspend?',
    'Where did I spend most?',
    'Can I afford a ₹2,000 jacket?',
    'How much did I spend on food this month?',
    'What subscriptions do I have?',
  ];

  void _send(AppState state, String q) {
    if (q.trim().isEmpty) return;
    _controller.clear();
    state.ask(q.trim());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final scheme = Theme.of(context).colorScheme;
    return Column(children: [
      Expanded(
        child: state.chat.isEmpty
            ? ListView(padding: const EdgeInsets.all(16), children: [
                Text('Ask about your spending. Every number in an answer comes from your own data.',
                    style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 12),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final e in _examples)
                    ActionChip(label: Text(e), onPressed: () => _send(state, e)),
                ]),
              ])
            : ListView(padding: const EdgeInsets.all(16), children: [
                for (final turn in state.chat) ...[
                  Align(
                    alignment: Alignment.centerRight,
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 8, left: 48),
                      decoration: BoxDecoration(
                          color: scheme.primaryContainer, borderRadius: BorderRadius.circular(12)),
                      child: Text(turn.question),
                    ),
                  ),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 16, right: 48),
                      decoration: BoxDecoration(
                          color: scheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(12)),
                      child: turn.answer == null && turn.error == null
                          ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
                          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(turn.error ?? turn.answer!),
                              if (turn.facts.isNotEmpty) ...[
                                const SizedBox(height: 8),
                                Wrap(spacing: 6, runSpacing: 6, children: [
                                  for (final f in turn.facts)
                                    Chip(
                                      visualDensity: VisualDensity.compact,
                                      label: Text('${f['label']}: ${f['value']}'),
                                    ),
                                ]),
                              ],
                            ]),
                    ),
                  ),
                ],
              ]),
      ),
      SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
          child: Row(children: [
            Expanded(
              child: TextField(
                controller: _controller,
                textInputAction: TextInputAction.send,
                maxLength: 500, // the server's limit
                onSubmitted: (q) => _send(state, q),
                decoration: const InputDecoration(
                    hintText: 'Ask a question', border: OutlineInputBorder(), counterText: ''),
              ),
            ),
            IconButton(icon: const Icon(Icons.send), onPressed: () => _send(state, _controller.text)),
          ]),
        ),
      ),
    ]);
  }
}
