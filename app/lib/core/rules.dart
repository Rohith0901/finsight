// Shared contracts (shared/*.json, copied into assets/shared by
// `make fixtures`). test/assets_parity_test.dart fails if the copies drift.

import 'dart:convert';

class MerchantEntry {
  MerchantEntry(this.id, this.name, this.category, this.aliases);
  final String id;
  final String name;
  final String category;
  final List<String> aliases;
}

class Category {
  const Category(this.id, this.name);
  final String id;
  final String name;
}

class SharedRules {
  SharedRules({
    required this.merchants,
    required this.cardBillAliases,
    required this.substringMinLength,
    required this.legalSuffixes,
    required this.businessWords,
    required this.personMinTokens,
    required this.personMaxTokens,
    required this.qrHandlePrefixes,
    required this.qrHandlePattern,
    required this.businessPspMarkers,
    required this.personalPsps,
    required this.singleTokenPersonMinLength,
    required this.hints,
    required this.categories,
  });

  final List<MerchantEntry> merchants;
  final List<String> cardBillAliases;
  final int substringMinLength;
  final List<String> legalSuffixes;
  final Set<String> businessWords;
  final int personMinTokens;
  final int personMaxTokens;
  final List<String> qrHandlePrefixes;
  final RegExp qrHandlePattern;
  final List<String> businessPspMarkers;
  final Set<String> personalPsps;
  final int singleTokenPersonMinLength;
  final Map<String, RegExp> hints;
  final List<Category> categories;

  String categoryName(String? id) {
    if (id == null || id == 'unknown') return 'Uncategorised';
    for (final c in categories) {
      if (c.id == id) return c.name;
    }
    return id;
  }

  factory SharedRules.fromJson({
    required String merchantsJson,
    required String hintsJson,
    required String categoriesJson,
  }) {
    final m = jsonDecode(merchantsJson) as Map<String, dynamic>;
    final names = m['names'] as Map<String, dynamic>;
    final vpa = m['vpa'] as Map<String, dynamic>;
    final h = (jsonDecode(hintsJson) as Map<String, dynamic>)['hints'] as Map<String, dynamic>;
    final c = (jsonDecode(categoriesJson) as Map<String, dynamic>)['categories'] as List;
    List<String> strings(dynamic v) => (v as List).map((e) => e as String).toList();
    return SharedRules(
      merchants: [
        for (final e in m['merchants'] as List)
          MerchantEntry(e['id'] as String, e['name'] as String, e['category'] as String,
              strings(e['aliases'])),
      ],
      cardBillAliases: strings(m['card_bill_aliases']),
      substringMinLength: (m['matching'] as Map<String, dynamic>)['substring_min_length'] as int,
      legalSuffixes: strings(names['legal_suffixes']),
      businessWords: strings(names['business_words']).toSet(),
      personMinTokens: names['person_min_tokens'] as int,
      personMaxTokens: names['person_max_tokens'] as int,
      qrHandlePrefixes: strings(vpa['qr_handle_prefixes']),
      qrHandlePattern: RegExp(vpa['qr_handle_pattern'] as String),
      businessPspMarkers: strings(vpa['business_psp_markers']),
      personalPsps: strings(vpa['personal_psps']).toSet(),
      singleTokenPersonMinLength: vpa['single_token_person_min_length'] as int,
      hints: {
        for (final e in h.entries) e.key: RegExp(e.value as String, caseSensitive: false),
      },
      categories: [for (final e in c) Category(e['id'] as String, e['name'] as String)],
    );
  }
}
