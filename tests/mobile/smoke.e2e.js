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

  // Commit 155 — ChordDiagram native smoke. The study/slow/play diagrams only
  // render when a live theory annotation exists, so assert against the
  // deterministic design-preview matrix (same component, session sizes).
  it("shows ChordDiagram matrix with sane dimensions", async () => {
    await device.openURL("harmoniq://design-preview");

    const diagram = element(by.id("chord-diagram")).atIndex(0);
    await expect(diagram).toBeVisible();

    const attrs = await diagram.getAttributes();
    const width = Number(attrs.width);
    const height = Number(attrs.height);
    if (!Number.isFinite(width) || width <= 0) {
      throw new Error(`[smoke] chord-diagram has non-sane width: ${attrs.width}`);
    }
    if (!Number.isFinite(height) || height <= 0) {
      throw new Error(`[smoke] chord-diagram has non-sane height: ${attrs.height}`);
    }
    // md diagram is ~110x100 logical px; cap generously for device pixels.
    if (width >= 2000 || height >= 2000) {
      throw new Error(`[smoke] chord-diagram implausibly large: ${width}x${height}`);
    }

    await device.takeScreenshot("chord-diagram-matrix");
  });
});

