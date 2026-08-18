const { by, device, element, expect, waitFor } = require("detox");

// Commit 107 — native MusicXML corpus render gate (mirrors tests/ui/musicxml-render.spec.ts).
// The native WebView harness loads MusicXML through the same AlphaTab engine as web;
// rendering a corpus file without error is the semantic "no crash" check on device.
const CORPUS = [
  { name: "irregular-5-4", label: "corpus-title:irregular-5-4" },
  { name: "multi-voice-staff", label: "corpus-title:multi-voice-staff" },
];

describe("MusicXML corpus renders without crash (native)", () => {
  beforeAll(async () => {
    await device.launchApp({ newInstance: true, delete: true });
  });

  for (const { name, label } of CORPUS) {
    it(`renders corpus file: ${name}`, async () => {
      await device.openURL(`harmoniq://musicxml-render-test?file=${name}`);

      await waitFor(element(by.label(label)))
        .toBeVisible()
        .withTimeout(60_000);

      await expect(element(by.label("corpus-error")).atIndex(0)).not.toBeVisible();

      await device.takeScreenshot(`musicxml-corpus-${name}`);
    });
  }
});