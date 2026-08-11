# minifyEnabled is off for v1 (see build.gradle.kts) — this file is a
# placeholder so turning it on later doesn't require plumbing a new file
# through the release build type.

# kotlinx.serialization keeps its generated serializers via @Serializable;
# nothing extra needed for reflection-free models like ours.

# Room generates implementations at compile time (KSP) — no runtime
# reflection to preserve.
