# Safety Checklist (executable)

Backend: `docker compose exec backend pytest tests/safety -q`
Frontend: `cd frontend && npm run test`
Everything: `make verify-phase15`

| # | Invariant | Verified by |
|---|-----------|-------------|
| 1 | Paper mode is the default | test_01_paper_mode_is_default |
| 2 | Live order placement is disabled | test_02_live_order_placement_disabled |
| 3 | Paper broker is the only order-capable broker | test_03_paper_is_only_order_capable |
| 4 | Kill switch blocks all orders | test_04_kill_switch_blocks_orders |
| 5 | Kill switch suppresses strategy emission | test_05_kill_switch_suppresses_emission |
| 6 | Live broker stubs refuse place_order | test_06_live_stubs_refuse_place_order |
| 7 | Notifications log-only unless configured | test_08_notifications_log_only_by_default |
| 8 | Mode -> signal-status mapping correct | test_09_mode_status_mapping |
| 9 | Execution refuses any non-paper broker | test_10_execution_refuses_live_broker |
| 10 | Rejected signals never execute | test_11_rejected_signal_never_executes |
| 11 | Settings singleton enforced | test_12_settings_singleton |
| 12 | Paper mode places a paper order | test_13_paper_mode_places_paper_order |
| 13 | Risk veto marks the signal rejected | test_14_risk_veto_marks_signal_rejected |
| 14 | Env GLOBAL_KILL_SWITCH blocks orders, DB switch false | test_env_kill_switch_blocks_orders_without_db_kill_switch |
| 15 | Env GLOBAL_KILL_SWITCH suppresses emission, DB switch false | test_env_kill_switch_suppresses_emission_without_db_kill_switch |
| 16 | ARM LIVE typed confirm required to leave paper (frontend) | ArmConfirmModal.test.tsx, confirm.test.ts |
| 17 | Kill switch is a fast single confirm (frontend) | KillSwitchControl.test.tsx |

Note: backtest Order/Position isolation (from the larger design) is OUT OF
SCOPE for this MVP because the backtesting engine is not included.
