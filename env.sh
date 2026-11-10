# Source this file before working: `source env.sh`
# Puts OSS CAD Suite tools and the project venv (cocotb) on PATH.

OSS_CAD_SUITE="${OSS_CAD_SUITE:-$HOME/tools/oss-cad-suite}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$OSS_CAD_SUITE/environment"
source "$REPO_ROOT/.venv/bin/activate"

# ~/.bashrc sources ROS Humble, whose PYTHONPATH packages break pytest and cocotb.
unset PYTHONPATH

# Terminals inside snap VS Code leak snap GTK paths, which break GTKWave.
unset GTK_PATH GTK_EXE_PREFIX GIO_MODULE_DIR GTK_IM_MODULE_FILE LOCPATH \
      GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR
