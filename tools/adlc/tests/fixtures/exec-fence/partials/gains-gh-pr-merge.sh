# REQ-682 TASK-247 fixture: injected into a copy of partials/forge.sh as the first line of
# adlc_forge_pr_create's body. An admitted function that gains a merge must fail the audit.
  gh pr merge "$1" --squash
