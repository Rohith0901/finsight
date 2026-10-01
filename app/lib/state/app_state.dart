// The app's state and use cases. Screens read from here and call its methods.

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../core/rules.dart';
import '../data/models.dart';
import '../data/repository.dart';
import '../ingestion/pipeline.dart';
import '../ingestion/sms_source.dart';

class ChatTurn {
  ChatTurn(this.question, {this.answer, this.facts = const [], this.error, this.provider});
  final String question;
  String? answer;
  List<Map<String, dynamic>> facts;
  String? error;
  String? provider;
}

class AppState extends ChangeNotifier {
  AppState({
    required this.repo,
    required this.pipeline,
    required this.rules,
    this.inbox,
    this.demoJsonl,
    ApiClient Function(ServerConfig)? clientFactory,
  }) : _clientFactory = clientFactory ?? ((c) => ApiClient(c));

  final Repository repo;
  final IngestionPipeline pipeline;
  final SharedRules rules;
  final InboxSmsSource? inbox;
  final Future<String> Function()? demoJsonl;
  final ApiClient Function(ServerConfig) _clientFactory;

  List<Txn> transactions = [];
  Map<String, dynamic>? insights;
  DateTime? insightsAt;
  String? status; // one-line message for the UI
  bool busy = false;
  bool consented = false;
  bool hasSmsPermission = false;
  ServerConfig server = const ServerConfig(baseUrl: '', token: '', fingerprint: '');
  int? manualBalancePaise;
  int? smsBalancePaise;
  int savingsTargetPaise = 0;
  String assistantProvider = 'auto';
  final List<ChatTurn> chat = [];
  StreamSubscription<void>? _inboxWatch;
  Timer? _debounce;

  int? get balancePaise => manualBalancePaise ?? smsBalancePaise;

  ApiClient? _client;
  ServerConfig? _clientConfig;

  ApiClient? get _api {
    if (!server.isComplete) return null;
    if (_client == null || !identical(_clientConfig, server)) {
      _client?.close();
      _client = _clientFactory(server);
      _clientConfig = server;
    }
    return _client;
  }

  Future<void> load() async {
    consented = await repo.setting('consent_ts') != null;
    server = ServerConfig(
      baseUrl: await repo.setting('server_url') ?? '',
      token: await repo.setting('server_token') ?? '',
      fingerprint: await repo.setting('server_fingerprint') ?? '',
    );
    manualBalancePaise = int.tryParse(await repo.setting('manual_balance') ?? '');
    savingsTargetPaise = int.tryParse(await repo.setting('savings_target') ?? '') ?? 0;
    assistantProvider = await repo.setting('assistant_provider') ?? 'auto';
    final cached = await repo.cached('insights');
    if (cached != null) {
      insights = cached.$1;
      insightsAt = cached.$2;
    }
    if (inbox != null) hasSmsPermission = await inbox!.hasPermission();
    await _reload();
  }

  Future<void> _reload() async {
    transactions = await repo.recent();
    smsBalancePaise = await repo.knownBalance();
    notifyListeners();
  }

  Future<void> _run(String label, Future<void> Function() work) async {
    busy = true;
    status = label;
    notifyListeners();
    try {
      await work();
    } on ApiException catch (e) {
      status = e.message;
    } catch (e) {
      // Errors and exceptions alike: a bad response must not crash a tap.
      status = 'Something went wrong: ${e.runtimeType}';
    } finally {
      busy = false;
      await _reload();
    }
  }

  // ------------------------------------------------------------ consent, SMS

  Future<void> giveConsent() async {
    await repo.setSetting('consent_ts', DateTime.now().toIso8601String());
    consented = true;
    if (inbox != null) hasSmsPermission = await inbox!.requestPermission();
    notifyListeners();
    if (hasSmsPermission) {
      watchInbox();
      await scanInbox();
    }
  }

  void watchInbox() {
    if (inbox == null || !hasSmsPermission || _inboxWatch != null) return;
    _inboxWatch = inbox!.changes.listen((_) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(seconds: 2), () => scanInbox(quiet: true));
    });
  }

  Future<void> scanInbox({bool quiet = false}) async {
    if (inbox == null || !consented || !hasSmsPermission || busy) return;
    await _run(quiet ? 'Checking for new messages' : 'Reading bank messages', () async {
      final counts = await pipeline.syncFrom(inbox!);
      final added = counts[IngestStatus.inserted] ?? 0;
      status = added == 0 ? 'No new transactions' : 'Added $added transactions';
      if (added > 0) await _afterNewData();
    });
  }

  Future<void> loadDemo() async {
    if (demoJsonl == null) return;
    await _run('Loading demo data', () async {
      final counts = await pipeline.syncFrom(DemoSmsSource(await demoJsonl!()), tag: 'demo');
      status = 'Demo: ${counts[IngestStatus.inserted]} transactions, '
          '${counts[IngestStatus.rejected]} messages correctly ignored';
      await _afterNewData();
    });
  }

  Future<void> _afterNewData() async {
    final api = _api;
    if (api == null) return;
    await _categorizeIfPossible(api);
    await _refreshInsights(api);
  }

  // ------------------------------------------------------------ backend

  Future<void> _categorize(ApiClient api) async {
    final pending = await repo.pending();
    if (pending.isEmpty) return;
    for (final r in await api.classify(pending)) {
      final abstained = r['abstained'] == true;
      await repo.setCategory(int.parse(r['id'] as String), abstained ? 'unknown' : r['category'] as String,
          abstained ? 'unknown' : 'model', (r['confidence'] as num).toDouble());
    }
  }

  /// The model being unavailable (no trained model on the server) leaves
  /// those rows pending; insights still work from the rule-based categories.
  Future<void> _categorizeIfPossible(ApiClient api) async {
    try {
      await _categorize(api);
    } on ApiException catch (e) {
      if (e.code != 'model_unavailable') rethrow;
    }
  }

  Future<List<Txn>> _window() =>
      repo.since(DateTime.now().subtract(const Duration(days: 120)));

  Future<void> _refreshInsights(ApiClient api) async {
    final result = await api.insights(await _window(), DateTime.now(),
        balancePaise: balancePaise, savingsTargetPaise: savingsTargetPaise);
    await repo.cache('insights', result);
    insights = result;
    insightsAt = DateTime.now();
    status = 'Updated';
  }

  Future<void> refresh() async {
    final api = _api;
    if (api == null) {
      status = 'Add the server address, token and certificate fingerprint in Settings';
      notifyListeners();
      return;
    }
    await _run('Updating insights', () async {
      await _categorizeIfPossible(api);
      await _refreshInsights(api);
    });
  }

  Future<String> testConnection() async {
    final api = _api;
    if (api == null) return 'Fill in all three server fields first.';
    return await api.health() ? 'Connected' : 'Could not reach the server or the certificate did not match.';
  }

  Future<void> ask(String question) async {
    final turn = ChatTurn(question);
    chat.add(turn);
    notifyListeners();
    final api = _api;
    if (api == null) {
      turn.error = 'Connect to the server in Settings to ask questions.';
      notifyListeners();
      return;
    }
    try {
      final r = await api.chat(question, await _window(), DateTime.now(),
          balancePaise: balancePaise, savingsTargetPaise: savingsTargetPaise,
          provider: assistantProvider);
      turn.answer = r['answer'] as String;
      turn.facts = (r['facts'] as List).cast<Map<String, dynamic>>();
      turn.provider = r['provider_used'] as String?;
    } on ApiException catch (e) {
      turn.error = e.message;
    } catch (e) {
      turn.error = 'Something went wrong (${e.runtimeType}).';
    }
    notifyListeners();
  }

  // ------------------------------------------------------------ edits

  Future<void> correct(Txn t, String category) async {
    await repo.correct(t, category);
    await _reload();
  }

  Future<void> saveServer(ServerConfig c) async {
    var url = c.baseUrl.trim();
    if (url.isNotEmpty && !url.contains('://')) url = 'https://$url'; // "192.168.1.5:8443" works too
    c = ServerConfig(baseUrl: url, token: c.token, fingerprint: c.fingerprint);
    await repo.setSetting('server_url', c.baseUrl.trim());
    await repo.setSetting('server_token', c.token.trim());
    await repo.setSetting('server_fingerprint', normalizeFingerprint(c.fingerprint));
    server = ServerConfig(
        baseUrl: c.baseUrl.trim(), token: c.token.trim(),
        fingerprint: normalizeFingerprint(c.fingerprint));
    notifyListeners();
  }

  Future<void> saveMoney({int? manualBalance, required int savingsTarget}) async {
    await repo.setSetting('manual_balance', manualBalance?.toString());
    await repo.setSetting('savings_target', '$savingsTarget');
    manualBalancePaise = manualBalance;
    savingsTargetPaise = savingsTarget;
    notifyListeners();
  }

  Future<void> setAssistantProvider(String p) async {
    await repo.setSetting('assistant_provider', p);
    assistantProvider = p;
    notifyListeners();
  }

  Future<void> deleteEverything() async {
    _debounce?.cancel();
    _debounce = null;
    await repo.wipe();
    await _inboxWatch?.cancel();
    _inboxWatch = null;
    _client?.close();
    _client = null;
    _clientConfig = null;
    server = const ServerConfig(baseUrl: '', token: '', fingerprint: '');
    manualBalancePaise = null;
    savingsTargetPaise = 0;
    assistantProvider = 'auto';
    insights = null;
    insightsAt = null;
    chat.clear();
    consented = false;
    status = 'All FinSight data on this phone was deleted';
    await _reload();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _inboxWatch?.cancel();
    _client?.close();
    super.dispose();
  }
}
