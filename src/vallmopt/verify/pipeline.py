"""Staged verification pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from vallmopt.logging.schema import VerifyGateResult, VerifyRecord, git_commit
from vallmopt.utils.hashing import sha256_file
from vallmopt.utils.paths import ensure_dir
from vallmopt.verify.compile import compile_source
from vallmopt.verify.output import compare_candidate_to_reference
from vallmopt.verify.runtime import run_binary
from vallmopt.verify.safety import check_safety_file
from vallmopt.verify.sanitizer import run_sanitizer_gate


class VerifyPipeline:
    """Run compile, runtime, output, sanitizer, and safety gates in order."""

    gate_order = ["compile", "runtime", "output", "sanitizer", "safety"]

    def __init__(self, config: dict[str, Any] | None = None, *, dry_run: bool = False):
        self.config = config or {}
        self.dry_run = dry_run

    def run(
        self,
        *,
        kernel_name: str,
        arch_tag: str,
        isa: str,
        reference_path: str | Path,
        candidate_path: str | Path,
        work_dir: str | Path,
        compiler_flags: Sequence[str] | None = None,
        runtime_args: Sequence[str] | None = None,
        prompt_hash: str | None = None,
        generator_name: str | None = None,
        model_name: str | None = None,
        config_path: str | None = None,
    ) -> VerifyRecord:
        """Run the staged verification pipeline."""

        reference_path = Path(reference_path)
        candidate_path = Path(candidate_path)
        work_dir = ensure_dir(work_dir)

        suffix = ".exe" if os.name == "nt" else ""
        candidate_binary = work_dir / f"candidate{suffix}"
        reference_binary = work_dir / f"reference{suffix}"
        sanitizer_binary = work_dir / f"candidate_san{suffix}"

        compile_cfg = self.config.get("compile", {})
        runtime_cfg = self.config.get("runtime", {})
        sanitizer_cfg = self.config.get("sanitizer", {})

        compile_cflags = list(compile_cfg.get("cflags", ["-O3"]))
        compile_cflags.extend(compiler_flags or [])
        compile_ldflags = list(compile_cfg.get("ldflags", []))
        runtime_args = list(runtime_args if runtime_args is not None else runtime_cfg.get("args", []))
        timeout_sec = float(runtime_cfg.get("timeout_sec", 10))

        gates: list[VerifyGateResult] = []

        compile_gate = compile_source(
            source=candidate_path,
            output=candidate_binary,
            compiler=str(compile_cfg.get("compiler", "gcc")),
            cflags=compile_cflags,
            ldflags=compile_ldflags,
            dry_run=self.dry_run,
        )
        gates.append(compile_gate)

        if compile_gate.status == "fail":
            gates.extend(self._skipped_after_failure("runtime", "output", "sanitizer", "safety"))
        else:
            runtime_gate = run_binary(
                binary=candidate_binary,
                args=runtime_args,
                timeout_sec=timeout_sec,
                dry_run=self.dry_run,
            )
            gates.append(runtime_gate)

            if runtime_gate.status == "fail":
                gates.extend(self._skipped_after_failure("output", "sanitizer", "safety"))
            else:
                output_gate = compare_candidate_to_reference(
                    reference_source=reference_path,
                    candidate_binary=candidate_binary,
                    reference_binary=reference_binary,
                    compiler=str(compile_cfg.get("compiler", "gcc")),
                    cflags=compile_cflags,
                    ldflags=compile_ldflags,
                    runtime_args=runtime_args,
                    timeout_sec=timeout_sec,
                    dry_run=self.dry_run,
                )
                gates.append(output_gate)

                if output_gate.status == "fail":
                    gates.extend(self._skipped_after_failure("sanitizer", "safety"))
                else:
                    sanitizer_gate = run_sanitizer_gate(
                        source=candidate_path,
                        output=sanitizer_binary,
                        compiler=str(sanitizer_cfg.get("compiler", "clang")),
                        cflags=sanitizer_cfg.get("cflags"),
                        ldflags=sanitizer_cfg.get("ldflags"),
                        runtime_args=runtime_args,
                        timeout_sec=timeout_sec,
                        dry_run=self.dry_run,
                    )
                    gates.append(sanitizer_gate)

                    if sanitizer_gate.status == "fail":
                        gates.extend(self._skipped_after_failure("safety"))
                    else:
                        gates.append(check_safety_file(candidate_path))

        status, failure_reason = self._overall_status(gates)
        return VerifyRecord(
            kernel_name=kernel_name,
            arch_tag=arch_tag,
            isa=isa,
            generator_name=generator_name,
            model_name=model_name,
            prompt_hash=prompt_hash,
            reference_code_hash=sha256_file(reference_path),
            candidate_code_hash=sha256_file(candidate_path),
            status=status,
            gates=gates,
            git_commit=git_commit(),
            config_path=config_path,
            failure_reason=failure_reason,
            work_dir=str(work_dir),
            compiler_flags=compile_cflags,
            metadata={"dry_run": self.dry_run},
        )

    @staticmethod
    def _skipped_after_failure(*gate_names: str) -> list[VerifyGateResult]:
        return [
            VerifyGateResult(
                gate_name=gate_name,
                status="skipped",
                failure_reason="previous gate failed",
            )
            for gate_name in gate_names
        ]

    @staticmethod
    def _overall_status(gates: list[VerifyGateResult]) -> tuple[str, str | None]:
        for gate in gates:
            if gate.status == "fail":
                return "fail", gate.failure_reason
        if any(gate.status == "skipped" for gate in gates):
            return "skipped", "one or more gates were skipped"
        return "pass", None
