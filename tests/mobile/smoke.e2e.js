const { by, device, element, expect } = require("detox");

describe("Harmoniq mobile smoke flow", () => {
  beforeAll(async () => {
    await device.launchApp({ newInstance: true, delete: true });
  });

  beforeEach(async () => {
    await device.reloadReactNative();
  });

  it("boots and captures launch screenshot", async () => {
    const rootViewType =
      device.getPlatform() === "android"
        ? "com.facebook.react.ReactRootView"
        : "RCTRootView";

    await expect(element(by.type(rootViewType)).atIndex(0)).toBeVisible();
    await device.takeScreenshot("launch-root");
  });
});

