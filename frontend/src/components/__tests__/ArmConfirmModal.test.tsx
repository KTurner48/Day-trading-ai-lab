import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ArmConfirmModal } from "../ArmConfirmModal";

describe("ArmConfirmModal", () => {
  it("keeps Confirm disabled until ARM LIVE is typed exactly", () => {
    const onConfirm = vi.fn();
    render(<ArmConfirmModal open targetLabel="LIVE · MANUAL"
                            onConfirm={onConfirm} onClose={() => {}} />);
    const confirm = screen.getByRole("button", { name: /confirm/i });
    expect(confirm).toBeDisabled();

    const input = screen.getByLabelText("arm-phrase");
    fireEvent.change(input, { target: { value: "arm" } });
    expect(confirm).toBeDisabled();

    fireEvent.change(input, { target: { value: "arm live" } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("does not fire confirm on a wrong phrase", () => {
    const onConfirm = vi.fn();
    render(<ArmConfirmModal open targetLabel="LIVE · AUTO"
                            onConfirm={onConfirm} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("arm-phrase"), { target: { value: "GO LIVE" } });
    expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
