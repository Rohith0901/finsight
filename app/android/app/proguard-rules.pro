# SQLCipher (sqflite_sqlcipher) must survive code shrinking in release builds.
-keep class net.sqlcipher.** { *; }
-keep class net.zetetic.database.** { *; }
