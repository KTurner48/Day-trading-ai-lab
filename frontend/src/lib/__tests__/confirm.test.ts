import { describe, it, expect } from "vitest";
import { requiresArmConfirmation, isArmPhraseValid, ARM_PHRASE } from "../confirm";

describe("ARM LIVE confirmation logic", () => {
  it("requires confirmation for any non-paper target", () => {
    expect(requiresArmConfirmation("live_manual_approval")).toBe(true);
    expect(requiresArmConfirmation("live_auto")).toBe(true);
  });

  it("does NOT require confirmation to return to paper", () => {
    expect(requiresArmConfirmation("paper")).toBe(false);
  });

  it("accepts the exact phrase case-insensitively and trimmed", () => {
    expect(isArmPhraseValid("ARM LIVE")).toBe(true);
    expect(isArmPhraseValid("  arm live ")).toBe(true);
    expect(ARM_PHRASE).toBe("ARM LIVE");
  });

  it("rejects anything that is not the phrase", () => {
    expect(isArmPhraseValid("")).toBe(false);
    expect(isArmPhraseValid("arm")).toBe(false);
    expect(isArmPhraseValid("GO LIVE")).toBe(false);
  });
});
