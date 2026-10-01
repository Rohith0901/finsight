import 'package:flutter/material.dart';

const _seed = Color(0xFF0F766E); // deep teal

ThemeData buildTheme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(seedColor: _seed, brightness: brightness);
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    cardTheme: const CardThemeData(margin: EdgeInsets.zero),
    listTileTheme: const ListTileThemeData(contentPadding: EdgeInsets.symmetric(horizontal: 16)),
  );
}

/// One stable colour per category, readable in light and dark themes.
const categoryColors = <String, Color>{
  'food': Color(0xFFE76F51),
  'groceries': Color(0xFF2A9D8F),
  'transport': Color(0xFF457B9D),
  'shopping': Color(0xFFB5838D),
  'utilities': Color(0xFF8D99AE),
  'subscriptions': Color(0xFF7B2CBF),
  'health': Color(0xFF2B9348),
  'entertainment': Color(0xFFF4A261),
  'transfers': Color(0xFF6C757D),
  'income': Color(0xFF168AAD),
  'other': Color(0xFF9C6644),
  'unknown': Color(0xFFADB5BD),
};

const categoryIcons = <String, IconData>{
  'food': Icons.restaurant,
  'groceries': Icons.local_grocery_store,
  'transport': Icons.directions_car,
  'shopping': Icons.shopping_bag,
  'utilities': Icons.bolt,
  'subscriptions': Icons.autorenew,
  'health': Icons.local_hospital,
  'entertainment': Icons.movie,
  'transfers': Icons.swap_horiz,
  'income': Icons.savings,
  'other': Icons.category,
  'unknown': Icons.help_outline,
};

Color colorFor(String? category) => categoryColors[category ?? 'unknown'] ?? categoryColors['unknown']!;
IconData iconFor(String? category) => categoryIcons[category ?? 'unknown'] ?? Icons.help_outline;
