// Applies the Detox wiring that `expo prebuild` does not generate for android/.
// `android/` is a gitignored prebuild output, so `detox:build:android` runs this
// after (re)generating the project. Idempotent: each block is detected by its
// functional line, so re-runs and already-patched projects are no-ops.
const { readFileSync, writeFileSync } = require("node:fs");
const path = require("node:path");

const ANDROID_DIR = path.resolve(process.cwd(), "android");

function patch(file, apply) {
  const full = path.join(ANDROID_DIR, file);
  let content;
  try {
    content = readFileSync(full, "utf8");
  } catch {
    console.error(`[detox-patch] WARN: ${file} not found — did prebuild run?`);
    return false;
  }
  const next = apply(content);
  if (next !== content) {
    writeFileSync(full, next);
    console.log(`[detox-patch] patched ${file}`);
    return true;
  }
  return false;
}

let changed = 0;

// 1. settings.gradle — link the :detox project (its androidTest source set
//    holds DetoxTestRunner; without it the test APK has no runner).
changed += patch("settings.gradle", (c) => {
  if (c.includes("project(':detox')")) return c;
  return c.replace(
    "include ':app'",
    "include ':app'\n" +
      "include ':detox'\n" +
      "project(':detox').projectDir = new File(rootProject.projectDir, '../node_modules/detox/android/detox')"
  );
});

// 2. app/build.gradle — instrumentation runner, Detox test deps, JS-in-debug
//    bundling, and the androidTest APK jniLibs merge fix.
changed += patch("app/build.gradle", (c) => {
  let next = c;

  // Debug variant should embed the JS bundle so Detox never handshakes with
  // Metro at launch time.
  if (!next.includes("debuggableVariants = []")) {
    next = next.replace(
      "enableBundleCompression = (findProperty('android.enableBundleCompression') ?: false).toBoolean()",
      "enableBundleCompression = (findProperty('android.enableBundleCompression') ?: false).toBoolean()\n" +
        "    // [detox-patch] Bundle JS into the debug APK so Detox E2E runs without a live Metro.\n" +
        "    debuggableVariants = []"
    );
  }

  if (!next.includes('testInstrumentationRunner "androidx.test.runner.AndroidJUnitRunner"')) {
    next = next.replace(
      'buildConfigField "String", "REACT_NATIVE_RELEASE_LEVEL"',
      '// [detox-patch] Detox drives the app through this instrumentation.\n' +
        '        testInstrumentationRunner "androidx.test.runner.AndroidJUnitRunner"\n\n' +
        '        buildConfigField "String", "REACT_NATIVE_RELEASE_LEVEL"'
    );
  }

  if (!next.includes("androidTestImplementation(project(path: ':detox'")) {
    next = next.replace(
      "if (hermesEnabled.toBoolean()) {",
      "// [detox-patch] Detox test APK wiring (runner + JUnit4). The :detox\n" +
        "    // project has `full`/`coreNative` flavors; pin the `full` flavor via its\n" +
        "    // variant attribute so AGP picks fullDebug* elements for this dependency.\n" +
        "    androidTestImplementation(project(path: ':detox')) {\n" +
        "        attributes {\n" +
        "            attribute(Attribute.of(\"detox\", String), \"full\")\n" +
        "        }\n" +
        "    }\n" +
        "    androidTestImplementation('junit:junit:4.13.2')\n\n" +
        "    if (hermesEnabled.toBoolean()) {"
    );
  }

  if (!next.includes("pickFirsts += 'lib/**/libfbjni.so'")) {
    next = next.replace(
      "useLegacyPackaging enableLegacyPackaging.toBoolean()",
      "useLegacyPackaging enableLegacyPackaging.toBoolean()\n" +
        "            // [detox-patch] RN modules vendor libfbjni.so; the androidTest (Detox)\n" +
        "            // APK merge collides with react-android's copy.\n" +
        "            pickFirsts += 'lib/**/libfbjni.so'"
    );
  }

  return next;
});

// 3. Root build.gradle — androidTest (Detox) APK merge packaging fixes:
//    jniLibs (fbjni, libc++_shared) and META-INF resources collide when every
//    module's androidTest APK is merged against the app's dependencies.
changed += patch("build.gradle", (c) => {
  if (c.includes("ANDROID_TEST_JNI_PICK_FIRSTS")) return c;
  const block = `
// [detox-patch] androidTest (Detox) APK merge packaging fixes: apply
// pickFirst/exclude at every module's packaging level.
def ANDROID_TEST_JNI_PICK_FIRSTS = [
  'lib/**/libfbjni.so',
  'lib/**/libc++_shared.so',
]
def ANDROID_TEST_RES_PICK_FIRSTS = [
  'META-INF/**',
]
def ANDROID_TEST_RES_EXCLUDES = [
  'META-INF/AL2.0',
  'META-INF/LGPL2.1',
]
allprojects {
  afterEvaluate { p ->
    if (p.hasProperty('android') && p.android.hasProperty('packagingOptions')) {
      try {
        p.android.packagingOptions.jniLibs.pickFirsts += ANDROID_TEST_JNI_PICK_FIRSTS
        p.android.packagingOptions.resources.pickFirsts += ANDROID_TEST_RES_PICK_FIRSTS
        p.android.packagingOptions.resources.excludes += ANDROID_TEST_RES_EXCLUDES
      } catch (ignored) {
        // Some modules lock packaging config after evaluate; ignore.
      }
    }
  }
}
`;
  return c.replace('apply plugin: "expo-root-project"', block + '\napply plugin: "expo-root-project"');
});

console.log(changed > 0 ? `[detox-patch] ${changed} file(s) patched.` : "[detox-patch] android/ already fully wired — no changes.");
