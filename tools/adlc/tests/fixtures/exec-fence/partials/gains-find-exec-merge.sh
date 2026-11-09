# REQ-682 Phase-5 fixture: injected into a copy of partials/lessons.sh as the first line of
# adlc_lessons's body. A merge hidden behind `find -exec` must fail the audit.
  find . -name x -exec gh pr merge 1 \;
