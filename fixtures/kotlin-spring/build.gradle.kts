// Fixture only: the build script is never executed by the scanners
// (docs/14 — no repository code is run by default).
plugins {
    kotlin("jvm") version "2.0.0"
}

repositories {
    mavenCentral()
}
