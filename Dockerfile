# Reproducible environment: OSS CAD Suite (Verilator, Yosys, SymbiYosys, solvers),
# a Python venv with cocotb/pytest/numpy, and Lean 4 at the versions used in the README.
FROM ubuntu:24.04

ARG OSS_CAD_DATE=2026-11-10
ARG LEAN_TOOLCHAIN=leanprover/lean4:v4.35.0
ARG DEBIAN_FRONTEND=noninteractive

SHELL ["/bin/bash", "-c"]

# Check-Date=false: tolerate a host clock that is a few minutes behind (signatures are still verified).
RUN apt-get -o Acquire::Check-Date=false update && apt-get install -y --no-install-recommends \
        ca-certificates curl git make g++ bc python3 python3-venv python3-pip libpython3-dev\
    && rm -rf /var/lib/apt/lists/*

# OSS CAD Suite (release tag 2026-11-10 -> file name 20261110)
ENV OSS_CAD_SUITE=/opt/oss-cad-suite
RUN D="${OSS_CAD_DATE//-/}" && \
    curl -fsSL "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_DATE}/oss-cad-suite-linux-x64-${D}.tgz" \
    | tar -xz -C /opt

# Lean 4 via elan (pinned toolchain)
ENV HOME=/root
RUN curl -fsSL https://elan.lean-lang.org/elan-init.sh | sh -s -- -y --default-toolchain "${LEAN_TOOLCHAIN}" --no-modify-path

WORKDIR /work
COPY requirements.txt .
RUN python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .
# Windows checkouts may have CRLF line endings, which bash and elan cannot read.
RUN find . -path ./.venv -prune -o \( -name '*.sh' -o -name '*.sby' -o -name lean-toolchain \) -type f -print0 \
      | xargs -0 sed -i 's/$//' \
    && chmod +x formal/run_all.sh lean/check.sh synth/area_sweep.sh

# Fetch the Lean toolchain pinned in lean/lean-toolchain now, not at every run.
RUN cd lean && /root/.elan/bin/lean --version

# env.sh sets up PATH for every tool; run any command through it.
ENTRYPOINT ["/bin/bash", "-c", "source /work/env.sh && exec \"$@\"", "--"]
CMD ["pytest"]
