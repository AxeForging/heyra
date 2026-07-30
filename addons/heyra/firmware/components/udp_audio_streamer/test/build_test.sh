#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
g++ -std=c++17 -O1 -Wall -Wextra -I.. test_goertzel_t3.cpp ../goertzel.cpp ../t3_detector.cpp -o /tmp/heyra_core_test
/tmp/heyra_core_test
