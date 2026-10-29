#!/bin/sh
# literal-read-path.sh: a new partial that loads a sibling partial through a
# literal home-directory path, which the plugin route does not have (BR-13).
adlc_x_load() {
  . ~/.claude/skills/partials/x.sh
}
