const { by, device, element, expect, waitFor } = require("detox");

describe("Harmoniq mobile smoke flow", () => {
  // Keep app data: on a cold install expo-sqlite can stall the first JS boot
  // past Detox's ready timeout. The MusicXML suite runs first and warms the DB;
  // this suite only needs the shell and the design-preview route.
  beforeAll(async () => {
    await device.launchApp({ newInstance: true });
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
    await device.openURL({ url: "harmoniq://design-preview" });

    await waitFor(element(by.id("design-preview-scroll")))
      .toExist()
      .withTimeout(60_000);
    await element(by.id("design-preview-scroll")).scrollTo("top");

    const diagram = element(by.label("Chord diagram: G")).atIndex(0);
    await waitFor(diagram).toBeVisible().withTimeout(60_000);
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

  // Commit 168 — left-handed mirror parity. The deterministic design-preview
  // matrix renders both hands from explicit props, so no pref seeding is needed.
  it("renders right- and left-handed fretboards", async () => {
    await device.openURL({ url: "harmoniq://design-preview" });

    await waitFor(element(by.id("design-preview-scroll")))
      .toExist()
      .withTimeout(60_000);
    await element(by.id("design-preview-scroll")).scrollTo("top");

    await waitFor(element(by.id("fretboard-mirror-section")))
      .toExist()
      .withTimeout(60_000);

    await element(by.id("design-preview-scroll")).scroll(300, "down");
    await waitFor(element(by.id("fretboard-diagram")).atIndex(0))
      .toBeVisible()
      .withTimeout(60_000);
    await device.takeScreenshot("fretboard-right-hand");

    await element(by.id("design-preview-scroll")).scroll(350, "down");
    await waitFor(element(by.id("fretboard-diagram")).atIndex(1))
      .toBeVisible()
      .withTimeout(60_000);
    await device.takeScreenshot("fretboard-left-hand");
  });
});

