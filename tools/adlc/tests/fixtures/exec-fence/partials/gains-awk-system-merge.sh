# REQ-682 Phase-5 fixture: injected into a copy of partials/lessons.sh as the first line of
# adlc_lessons's body. A merge inside an awk program's system() must fail the audit.
  awk 'BEGIN { system("gh pr merge 1") }'
