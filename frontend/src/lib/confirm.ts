// Pure helpers for the safety confirmations, kept separate so they are
// unit-testable without rendering.
export const ARM_PHRASE = "ARM LIVE";

// Leaving paper (to any live-adjacent mode) requires the typed phrase.
export function requiresArmConfirmation(targetMode: string): boolean {
  return targetMode !== "paper";
}

// The typed text must match the phrase exactly (case-insensitive, trimmed).
export function isArmPhraseValid(text: string): boolean {
  return text.trim().toUpperCase() === ARM_PHRASE;
}
