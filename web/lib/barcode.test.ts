import { describe, expect, test } from "vitest";

import { addProductUrl, barcodeCandidates, expandUpcE, matchesBarcode } from "./barcode";

describe("expandUpcE", () => {
  test("puts the suppressed zeros back, by the sixth data digit", () => {
    expect(expandUpcE("04252614")).toBe("042100005264"); // x = 1
    expect(expandUpcE("01234505")).toBe("012000003455"); // x = 0
    expect(expandUpcE("01234531")).toBe("012300000451"); // x = 3
    expect(expandUpcE("01234543")).toBe("012340000053"); // x = 4
    expect(expandUpcE("01234558")).toBe("012345000058"); // x = 5
  });

  test("only number systems 0 and 1, eight digits", () => {
    expect(expandUpcE("21234558")).toBeNull();
    expect(expandUpcE("0123455")).toBeNull();
  });
});

describe("barcodeCandidates", () => {
  test("EAN-13 and UPC-A are looked up as read", () => {
    expect(barcodeCandidates("0016000275287", "ean_13")).toEqual(["0016000275287"]);
    expect(barcodeCandidates("016000275287", "upc_a")).toEqual(["016000275287"]);
  });

  test("UPC-E is tried long first, then as read", () => {
    expect(barcodeCandidates("04252614", "upc_e")).toEqual(["042100005264", "04252614"]);
  });

  test("an EAN-8 that is not a UPC-E is looked up as read", () => {
    expect(barcodeCandidates("96385074", "ean_8")).toEqual(["96385074"]);
  });

  test("anything else is not a retail barcode", () => {
    expect(barcodeCandidates("https://example.com", "qr_code")).toEqual([]);
    expect(barcodeCandidates("12345", "code_128")).toEqual([]);
  });
});

describe("matchesBarcode", () => {
  test("the same digits, leading zeros aside", () => {
    expect(matchesBarcode("016000275287", "0016000275287")).toBe(true);
    expect(matchesBarcode("0016000275287", "0016000275287")).toBe(true);
    expect(matchesBarcode("016000275287", "0016000275288")).toBe(false);
    expect(matchesBarcode("0000", "0")).toBe(false);
  });
});

test("the add-it link goes to Open Food Facts with the code", () => {
  expect(addProductUrl("0123456789012")).toBe(
    "https://world.openfoodfacts.org/cgi/product.pl?code=0123456789012",
  );
});
