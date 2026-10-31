import { expect, test, type Page } from "@playwright/test";

async function readGuitarHandPref(page: Page): Promise<string | null> {
  return page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("harmoniq_web_v1");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
    });

    try {
      return await new Promise<string | null>((resolve, reject) => {
        const tx = db.transaction("app_prefs", "readonly");
        const request = tx.objectStore("app_prefs").get("guitar_hand");
        request.onsuccess = () => {
          const row = request.result as { value?: string } | undefined;
          resolve(typeof row?.value === "string" ? row.value : null);
        };
        request.onerror = () => reject(request.error ?? new Error("IndexedDB read failed"));
      });
    } finally {
      db.close();
    }
  });
}

test("playing hand defaults to right and persists across reloads", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/settings");

  const right = page.getByRole("button", { name: "right", exact: true });
  const left = page.getByRole("button", { name: "left", exact: true });

  await expect(right).toBeVisible({ timeout: 15_000 });
  await expect(right).toHaveClass(/bg-amber-accent/);
  expect(await readGuitarHandPref(page)).toBeNull();

  await left.click();
  await expect(left).toHaveClass(/bg-amber-accent/);
  await expect(page.getByText("Playing hand set to left.")).toBeVisible();
  expect(await readGuitarHandPref(page)).toBe("left");

  await page.reload();
  await expect(left).toBeVisible({ timeout: 15_000 });
  await expect(left).toHaveClass(/bg-amber-accent/);
});

test("@visual fretboard mirrors for right- and left-handed modes", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/design-preview", { waitUntil: "domcontentloaded" });

  const boards = page.getByTestId("fretboard-diagram");
  await expect(boards).toHaveCount(2, { timeout: 30_000 });
  await expect(boards.first()).toBeVisible();

  await expect(boards.nth(0)).toHaveScreenshot("fretboard-right.png");
  await expect(boards.nth(1)).toHaveScreenshot("fretboard-left.png");

  const chordPair = page.getByTestId("chord-mirror-pair").getByTestId("chord-diagram");
  await expect(chordPair).toHaveCount(2);
  await expect(chordPair.nth(0)).toHaveScreenshot("chord-right.png");
  await expect(chordPair.nth(1)).toHaveScreenshot("chord-left.png");
});
