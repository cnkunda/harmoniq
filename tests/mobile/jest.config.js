module.exports = {
  rootDir: "../..",
  testMatch: ["<rootDir>/tests/mobile/**/*.e2e.js"],
  testTimeout: 180000,
  maxWorkers: 1,
  globalSetup: "detox/runners/jest/globalSetup",
  globalTeardown: "detox/runners/jest/globalTeardown",
  testEnvironment: "detox/runners/jest/testEnvironment",
  reporters: ["detox/runners/jest/reporter"],
  verbose: true,
};

