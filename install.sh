#!/usr/bin/env bash
# install.sh — install the past-paper-analysis suite as Claude Code skills.
#
# Usage:
#   ./install.sh                # default: core profile
#   ./install.sh core           # 1 orchestrator + 7 spokes
#   ./install.sh full           # core + verified Anthropic companions
#   ./install.sh --uninstall    # remove all suite symlinks
#   ./install.sh --dry-run      # print actions without executing
#
# Pattern lifted from OctavianYimingZhang/equity-research-suite (same
# author). See references/external-borrowings.md.
#
# What this does:
# 1. Verifies Python deps from requirements.txt are installed.
# 2. Symlinks each skills/<name>/ into ~/.claude/skills/<name>/.
# 3. (full only) Records optional companion skills the suite leans on.
# 4. Writes a manifest at ~/.claude/skills/.past-paper-suite-manifest
#    so subsequent install / uninstall runs know what was installed.

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_TARGET="${HOME}/.claude/skills"
MANIFEST_PATH="${SKILLS_TARGET}/.past-paper-suite-manifest"

CORE_SKILLS=(
  "past-paper-orchestrator"
  "paper-ingest"
  "kp-pattern-mapper"
  "stat-engine"
  "cheatsheet-writer"
  "drill-curator"
  "technique-coach"
  "report-renderer"
)

# Companions we lean on at full profile. These must already be installed
# elsewhere (typically via an Anthropic plugin); this script only logs the
# expectation, it does NOT install third-party skills.
COMPANIONS_FULL=(
  "anthropics-skills:pdf"
  "anthropics-skills:docx"
  "anthropics-skills:xlsx"
  "anthropics-skills:doc-coauthoring"
)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

PROFILE="core"
DRY_RUN=0
UNINSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    core|full)
      PROFILE="$1"
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --uninstall)
      UNINSTALL=1
      ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() {
  printf "[install] %s\n" "$*"
}

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf "  (dry-run) %s\n" "$*"
  else
    eval "$@"
  fi
}

require_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found in PATH; install Python 3.11+ first" >&2
    exit 1
  fi
  local version
  version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  log "found python3 ${version}"
}

verify_python_deps() {
  log "verifying Python dependencies"
  if ! python3 -c "import openpyxl, docx, numpy" 2>/dev/null; then
    log "missing dependencies; run: pip install -r ${REPO_ROOT}/requirements.txt"
    if [[ "${DRY_RUN}" -eq 0 ]]; then
      exit 1
    fi
  fi
}

ensure_target_dir() {
  if [[ ! -d "${SKILLS_TARGET}" ]]; then
    log "creating ${SKILLS_TARGET}"
    run "mkdir -p '${SKILLS_TARGET}'"
  fi
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

if [[ "${UNINSTALL}" -eq 1 ]]; then
  log "uninstalling past-paper-analysis suite"
  if [[ -f "${MANIFEST_PATH}" ]]; then
    while IFS= read -r line; do
      [[ -z "${line}" ]] && continue
      target="${SKILLS_TARGET}/${line}"
      if [[ -L "${target}" ]]; then
        log "removing symlink ${target}"
        run "rm '${target}'"
      else
        log "skipping ${target} (not a symlink we created)"
      fi
    done < "${MANIFEST_PATH}"
    log "removing manifest"
    run "rm '${MANIFEST_PATH}'"
  else
    log "no manifest found at ${MANIFEST_PATH}; falling back to known skill names"
    for skill in "${CORE_SKILLS[@]}"; do
      target="${SKILLS_TARGET}/${skill}"
      if [[ -L "${target}" && "$(readlink "${target}")" == "${REPO_ROOT}/skills/${skill}" ]]; then
        log "removing symlink ${target}"
        run "rm '${target}'"
      fi
    done
  fi
  log "uninstall complete"
  exit 0
fi

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

log "installing past-paper-analysis suite (profile: ${PROFILE})"
require_python
verify_python_deps
ensure_target_dir

installed_names=()

for skill in "${CORE_SKILLS[@]}"; do
  src="${REPO_ROOT}/skills/${skill}"
  target="${SKILLS_TARGET}/${skill}"

  if [[ ! -d "${src}" ]]; then
    echo "missing source skill: ${src}" >&2
    exit 1
  fi

  if [[ -L "${target}" ]]; then
    existing="$(readlink "${target}")"
    if [[ "${existing}" == "${src}" ]]; then
      log "${skill}: already linked"
      installed_names+=("${skill}")
      continue
    fi
    log "${skill}: replacing stale symlink"
    run "rm '${target}'"
  elif [[ -e "${target}" ]]; then
    echo "${target} exists and is not our symlink; refusing to overwrite" >&2
    exit 1
  fi

  log "${skill}: linking ${src} -> ${target}"
  run "ln -s '${src}' '${target}'"
  installed_names+=("${skill}")
done

if [[ "${PROFILE}" == "full" ]]; then
  log "profile=full — verifying Anthropic companions are reachable"
  for companion in "${COMPANIONS_FULL[@]}"; do
    if [[ -d "${SKILLS_TARGET}/${companion//:/__}" ]] \
        || [[ -d "${SKILLS_TARGET}/${companion#anthropics-skills:}" ]]; then
      log "  ${companion}: present"
    else
      log "  ${companion}: NOT FOUND in ${SKILLS_TARGET} — install via Anthropic plugin manifest, then rerun"
    fi
  done
fi

# Write manifest of skills we installed (one per line) so --uninstall is
# clean later.
if [[ "${DRY_RUN}" -eq 0 ]]; then
  printf "%s\n" "${installed_names[@]}" > "${MANIFEST_PATH}"
  log "wrote manifest: ${MANIFEST_PATH}"
fi

log "install complete. Try: claude past-paper-orchestrator --help"
