// Merchant-name normalisation: the Dart twin of ml/finsight_ml/names.py.
// Both must reproduce shared/fixtures/merchant_name_cases.json exactly.

import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../core/rules.dart';

final _nonAlnum = RegExp(r'[^a-z0-9]+');
final _digits = RegExp(r'[0-9]+');
final _alpha = RegExp(r'^[a-z]+$');
final _allDigits = RegExp(r'^[0-9]+$');

String normalizeText(String? text) =>
    (text ?? '').toLowerCase().replaceAll(_nonAlnum, ' ').trim();

class MerchantName {
  const MerchantName(this.kind, this.key, this.display, [this.category]);

  /// "known" | "merchant" | "person" | "qr" | "unknown"
  final String kind;

  /// merchant_norm sent to the backend ("" when unknown); persons get a pseudonym.
  final String key;
  final String display;
  final String? category;
}

class _Alias {
  _Alias(this.compact, this.tokens, this.merchant);
  final String compact;
  final List<String> tokens;
  final MerchantEntry merchant;
}

class Normalizer {
  Normalizer(this.rules, this.salt)
      : _aliases = [
          for (final m in rules.merchants)
            for (final a in m.aliases)
              _Alias(normalizeText(a).replaceAll(' ', ''), normalizeText(a).split(' '), m),
        ];

  final SharedRules rules;

  /// Per-install secret: the same payee always gets the same pseudonym on this
  /// phone, and the pseudonym reveals nothing off it.
  final String salt;
  final List<_Alias> _aliases;

  static bool _hasTokenRun(List<String> tokens, List<String> run) {
    for (var i = 0; i + run.length <= tokens.length; i++) {
      var ok = true;
      for (var j = 0; j < run.length; j++) {
        if (tokens[i + j] != run[j]) {
          ok = false;
          break;
        }
      }
      if (ok) return true;
    }
    return false;
  }

  bool _aliasHits(String compactAlias, List<String> aliasTokens, String compact,
      List<String> tokens) {
    return compactAlias.length >= rules.substringMinLength
        ? compact.contains(compactAlias)
        : _hasTokenRun(tokens, aliasTokens);
  }

  MerchantEntry? matchKnown(String text) {
    final n = normalizeText(text);
    if (n.isEmpty) return null;
    final tokens = n.split(' ');
    final compact = n.replaceAll(' ', '');
    _Alias? best;
    for (final a in _aliases) {
      if (_aliasHits(a.compact, a.tokens, compact, tokens) &&
          (best == null || a.compact.length > best.compact.length)) {
        best = a;
      }
    }
    return best?.merchant;
  }

  bool isCardBillName(String text) {
    final n = normalizeText(text);
    final tokens = n.split(' ');
    final compact = n.replaceAll(' ', '');
    for (final alias in rules.cardBillAliases) {
      final a = normalizeText(alias);
      if (_aliasHits(a.replaceAll(' ', ''), a.split(' '), compact, tokens)) return true;
    }
    return false;
  }

  String stripLegalSuffixes(String n) {
    final suffixes = [...rules.legalSuffixes]..sort((a, b) => b.length.compareTo(a.length));
    var changed = true;
    while (changed) {
      changed = false;
      for (final suf in suffixes) {
        if (n.endsWith(' $suf')) {
          n = n.substring(0, n.length - suf.length - 1).trim();
          changed = true;
          break;
        }
      }
    }
    return n;
  }

  bool _looksLikePerson(List<String> tokens) =>
      tokens.length >= rules.personMinTokens &&
      tokens.length <= rules.personMaxTokens &&
      tokens.every(_alpha.hasMatch) &&
      tokens.any((t) => t.length >= 3) &&
      !tokens.any(rules.businessWords.contains);

  /// One alphabetic word ("aishwaryakhan") with no 4+ letter business word inside.
  bool _singleWordPerson(List<String> tokens) =>
      tokens.length == 1 &&
      _alpha.hasMatch(tokens.single) &&
      tokens.single.length >= rules.singleTokenPersonMinLength &&
      !rules.businessWords.any((w) => w.length >= 4 && tokens.single.contains(w));

  String personKey(String name) {
    final digest = Hmac(sha256, utf8.encode(salt)).convert(utf8.encode(normalizeText(name)));
    return 'person:${digest.toString().substring(0, 10)}';
  }

  static String _title(List<String> tokens) => tokens
      .where((t) => t.isNotEmpty)
      .map((t) => t[0].toUpperCase() + t.substring(1))
      .join(' ');

  MerchantName resolve(String? raw, {bool p2a = false, bool p2m = false}) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return const MerchantName('unknown', '', 'Unknown');
    if (text.contains('@')) {
      final lower = text.toLowerCase();
      final at = lower.indexOf('@');
      final handle = lower.substring(0, at);
      final psp = lower.substring(at + 1);
      if (_allDigits.hasMatch(handle) && handle.length >= 10) {
        return MerchantName('person', personKey(handle), 'UPI user');
      }
      if (rules.qrHandlePrefixes.any(handle.startsWith) || rules.qrHandlePattern.hasMatch(handle)) {
        return const MerchantName('qr', '', 'UPI merchant');
      }
      final known = matchKnown(handle);
      if (known != null) return MerchantName('known', known.id, known.name, known.category);
      // Digits come off before the person check, so "rahul.sharma99@okhdfcbank"
      // is recognised as a person (and pseudonymised) rather than sent as a name.
      final n = normalizeText(handle.replaceAll(_digits, ' '));
      final tokens = n.isEmpty ? <String>[] : n.split(' ');
      final businessPsp = rules.businessPspMarkers.any(psp.contains);
      if (!businessPsp && !p2m && (p2a ||
              (rules.personalPsps.contains(psp) &&
                  (_looksLikePerson(tokens) || _singleWordPerson(tokens))))) {
        return MerchantName('person', personKey(tokens.join(' ')), _title(tokens));
      }
      final key = normalizeText(handle.replaceAll(_digits, ' '));
      return key.isEmpty
          ? const MerchantName('qr', '', 'UPI merchant')
          : MerchantName('merchant', key, _title(key.split(' ')));
    }
    final known = matchKnown(text);
    if (known != null) return MerchantName('known', known.id, known.name, known.category);
    final n = stripLegalSuffixes(normalizeText(text));
    final tokens = n.isEmpty ? <String>[] : n.split(' ');
    if (!p2m && (p2a || _looksLikePerson(tokens))) {
      return MerchantName('person', personKey(n), _title(tokens));
    }
    return n.isEmpty
        ? const MerchantName('unknown', '', 'Unknown')
        : MerchantName('merchant', n, _title(tokens));
  }
}
