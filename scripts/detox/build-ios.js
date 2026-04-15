const { existsSync } = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...options,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (process.platform === "win32") {
  console.error("iOS Detox build requires macOS with Xcode. Use this config in macOS CI.");
  process.exit(1);
}

if (!existsSync(path.resolve(process.cwd(), "ios"))) {
  run("npx", ["expo", "prebuild", "--platform", "ios", "--non-interactive"]);
}

const appName = process.env.DETOX_IOS_APP_NAME || "Harmoniq";
run("xcodebuild", [
  "-workspace",
  `ios/${appName}.xcworkspace`,
  "-scheme",
  appName,
  "-configuration",
  "Debug",
  "-sdk",
  "iphonesimulator",
  "-derivedDataPath",
  "ios/build",
]);

