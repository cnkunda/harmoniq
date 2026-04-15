/** @type {import('detox').DetoxConfig} */
module.exports = {
  testRunner: {
    args: {
      $0: "jest",
      config: "tests/mobile/jest.config.js",
    },
    jest: {
      setupTimeout: 180000,
    },
  },
  apps: {
    "android.debug": {
      type: "android.apk",
      binaryPath: "android/app/build/outputs/apk/debug/app-debug.apk",
      testBinaryPath: "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
      build: "node ./scripts/detox/build-android.js",
      reversePorts: [8081],
    },
    "ios.debug": {
      type: "ios.app",
      binaryPath: "ios/build/Build/Products/Debug-iphonesimulator/Harmoniq.app",
      build: "node ./scripts/detox/build-ios.js",
    },
  },
  devices: {
    emulator: {
      type: "android.emulator",
      device: {
        avdName: process.env.DETOX_ANDROID_AVD || "Pixel_7_API_34",
      },
    },
    simulator: {
      type: "ios.simulator",
      device: {
        type: process.env.DETOX_IOS_SIMULATOR || "iPhone 15",
      },
    },
  },
  configurations: {
    "android.emu.debug": {
      device: "emulator",
      app: "android.debug",
    },
    "ios.sim.debug": {
      device: "simulator",
      app: "ios.debug",
    },
  },
};

