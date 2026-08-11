// Root build file — plugin versions are declared here (apply false) and
// actually applied per-module in app/build.gradle.kts. Mirrors the
// desktop app's separation of concerns: this file only wires tooling.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
}
