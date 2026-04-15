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

if (!existsSync(path.resolve(process.cwd(), "android"))) {
  run("npx", ["expo", "prebuild", "--platform", "android", "--non-interactive"]);
}

const gradleWrapper = process.platform === "win32" ? "gradlew.bat" : "./gradlew";
run(gradleWrapper, ["assembleDebug", "assembleAndroidTest", "-DtestBuildType=debug"], {
  cwd: path.resolve(process.cwd(), "android"),
});

