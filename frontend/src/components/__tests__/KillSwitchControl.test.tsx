import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("../../lib/api", () => ({
  api: { setKillSwitch: vi.fn().mockResolvedValue({ kill_switch_active: true }) },
}));

import { api } from "../../lib/api";
import { KillSwitchControl } from "../KillSwitchControl";

describe("KillSwitchControl", () => {
  beforeEach(() => vi.clearAllMocks());

  it("engages with a single confirm — no typed phrase required", async () => {
    render(<KillSwitchControl active={false} onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /engage kill switch/i }));
    // A single confirm dialog with one click; assert there is NO text input.
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /halt now/i }));
    await waitFor(() =>
      expect(api.setKillSwitch).toHaveBeenCalledWith(true, expect.any(String)),
    );
  });

  it("shows halted state and allows release", async () => {
    render(<KillSwitchControl active={true} onChanged={() => {}} />);
    expect(screen.getByText(/halted/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /release halt/i }));
    await waitFor(() =>
      expect(api.setKillSwitch).toHaveBeenCalledWith(false, expect.any(String)),
    );
  });
});
