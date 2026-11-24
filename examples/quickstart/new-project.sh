#!/bin/sh
# new-project.sh: make a new project from the ADLC quickstart sample (REQ-672 ADR-3).
#
#   sh new-project.sh NAME
#   sh new-project.sh NAME --existing-repo OWNER/REPO
#
# Copies sample/, which sits next to this script, into a new directory NAME in
# the current directory, makes the first commit on main, then gives it a GitHub
# remote: `gh repo create NAME --private --source NAME --push`, or, with
# --existing-repo, that repository (it must be empty) added as origin and
# pushed. OWNER and REPO are each letters, digits, '.', '_' and '-', and start
# with neither '.' nor '-'. It refuses, and creates nothing, when NAME already
# exists, when git or gh is not on PATH, when git has no name and email, or when
# gh is not signed in to github.com.
#
# It never reads or prints a token: gh, and git through gh's credential helper,
# handle sign-in themselves.
#
# Exit status: 0 done, 1 refused or failed, 2 usage error.

prog=new-project
usage="usage: sh new-project.sh NAME [--existing-repo OWNER/REPO]"

say() {
  printf '%s: %s\n' "$prog" "$*"
}

# refuse CODE MESSAGE: print MESSAGE on stderr and exit with CODE.
refuse() {
  code=$1
  shift
  printf '%s: %s\n' "$prog" "$*" >&2
  exit "$code"
}

name=""
existing=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --existing-repo)
      [ "$#" -ge 2 ] || refuse 2 "--existing-repo needs OWNER/REPO. $usage"
      existing=$2
      shift 2
      ;;
    --existing-repo=*)
      existing=${1#--existing-repo=}
      shift
      ;;
    -h|--help)
      printf '%s\n' "$usage"
      exit 0
      ;;
    -*)
      refuse 2 "unknown option '$1'. $usage"
      ;;
    *)
      [ -z "$name" ] || refuse 2 "give one project name, not '$name' and '$1'. $usage"
      name=$1
      shift
      ;;
  esac
done

[ -n "$name" ] || refuse 2 "no project name given. $usage"
case "$name" in
  .*|*[!A-Za-z0-9._-]*)
    refuse 2 "'$name' is not a usable project name: use letters, digits, '.', '_' and '-', and do not start with '.'."
    ;;
esac
# part_ok PART: true when PART is a usable OWNER or REPO: letters, digits, '.',
# '_' and '-', not empty, and not starting with '.' or '-' (so never '.' or '..').
part_ok() {
  case "$1" in
    ''|.*|-*|*[!A-Za-z0-9._-]*)
      return 1
      ;;
  esac
  return 0
}

if [ -n "$existing" ]; then
  owner=${existing%%/*}
  repo=${existing#*/}
  if [ "$owner" = "$existing" ] || ! part_ok "$owner" || ! part_ok "$repo"; then
    refuse 2 "--existing-repo wants OWNER/REPO, not '$existing'. Each part is letters, digits, '.', '_' and '-', and starts with neither '.' nor '-'."
  fi
fi

missing=0
if ! command -v git >/dev/null 2>&1; then
  printf '%s: %s\n' "$prog" "git is not on PATH. Install git, then run this again." >&2
  missing=1
fi
if ! command -v gh >/dev/null 2>&1; then
  printf '%s: %s\n' "$prog" "gh, the GitHub CLI, is not on PATH. Install it from https://cli.github.com and sign in with 'gh auth login', then run this again." >&2
  missing=1
fi
[ "$missing" -eq 0 ] || refuse 1 "nothing was changed."

sample="$(dirname "$0")/sample"
[ -d "$sample" ] || refuse 1 "the sample project is not at '$sample'. Run this script from the toolkit copy that holds it. Nothing was changed."

if [ -e "$name" ] || [ -L "$name" ]; then
  refuse 1 "'$name' already exists here. Choose another name, or remove it first. Nothing was changed."
fi

git var GIT_AUTHOR_IDENT >/dev/null 2>&1 ||
  refuse 1 "git does not know your name and email. Set them with 'git config --global user.name' and 'git config --global user.email', then run this again. Nothing was changed."

gh auth status --hostname github.com >/dev/null 2>&1 ||
  refuse 1 "gh is not signed in to github.com. Run 'gh auth login', then run this again. Nothing was changed."

mkdir "$name" || refuse 1 "could not create '$name'. Nothing was changed."
here=$(pwd)
project="$here/$name"

if ! cp -R "$sample/." "$project"; then
  refuse 1 "copying the sample into '$project' failed. Remove '$project', then run this again."
fi
if ! { git init -q "$project" &&
       git -C "$project" symbolic-ref HEAD refs/heads/main &&
       git -C "$project" add -A &&
       git -C "$project" commit -q -m "Start from the ADLC quickstart sample"; }; then
  refuse 1 "making the first commit in '$project' failed. Remove '$project', then run this again."
fi
say "copied the sample into $name and made the first commit on main"

if [ -z "$existing" ]; then
  say "creating the private GitHub repository $name and pushing main to it"
  if ! gh repo create "$name" --private --source "$name" --push; then
    printf '%s: %s\n' "$prog" "gh repo create failed, so '$name' has no GitHub remote yet. The project and its first commit are in '$project'." >&2
    refuse 1 "to finish by hand, fix what gh reported, then run: cd '$project' && gh repo create '$name' --private --source . --push"
  fi
else
  say "adding $existing as origin and pushing main to it"
  if ! { git -C "$project" remote add origin "https://github.com/$existing.git" &&
         git -C "$project" -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -q -u origin main; }; then
    printf '%s: %s\n' "$prog" "pushing to $existing failed. It must be an empty repository you can push to. The project and its first commit are in '$project'." >&2
    refuse 1 "to finish by hand, run: cd '$project' && git push -u origin main"
  fi
fi

say "$name is ready. Next: cd $name"
