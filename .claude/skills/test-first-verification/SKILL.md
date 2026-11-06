---
name: test-first-verification
description: Use for every coding task. Requires a regression test and a verified test run before you claim completion.
---
- Before editing, write or identify the test that fails because of the bug.
- After editing, run the full suite (python tests/test_indian_market.py) and
  paste the actual result. Never write "tests pass" without running them.
- Add tests for: API response shape (what the frontend reads), failure of
  each external call, boundary times (09:14/09:15/15:10/15:30), and both
  trade sides.
- No test may depend on the live network; use recorded fixtures.
- End every task with: files changed, tests added, test output, remaining
  risks.

