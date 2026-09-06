#!/bin/sh
# Local release installer. Homebrew owns Python and the application environment.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh, then run this installer again." >&2
  exit 1
fi
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
export HOMEBREW_NO_INSTALL_UPGRADE=1
python_prefix=$(brew --prefix python@3.14)
if [ ! -x "$python_prefix/bin/python3.14" ]; then
  brew install python@3.14
fi
exec "$python_prefix/bin/python3.14" "$root/tools/homebrew.py" install "$@"
