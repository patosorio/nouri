"""RepairStrategy — structured repair hints for PlanGeneratorAgent re-calls."""

from __future__ import annotations

from validation.types import CheckResult, RepairInstruction, RepairInstructions


class RepairStrategy:
    def build_repair_instructions(
        self, validation_results: list[CheckResult] | tuple[CheckResult, ...]
    ) -> RepairInstructions:
        instructions: list[RepairInstruction] = []
        for result in validation_results:
            if result.passed:
                continue
            hints = result.repair_hints or result.errors
            if not hints:
                instructions.append(
                    RepairInstruction(
                        checker=result.checker,
                        guidance=f"{result.checker} failed; regenerate to satisfy constraints.",
                    )
                )
                continue
            for hint in hints:
                instructions.append(
                    RepairInstruction(checker=result.checker, guidance=hint)
                )
        return RepairInstructions(instructions=tuple(instructions))

    # Alias matching docs/7_TECH_SPEC.md §6.1 naming
    def build_instructions(
        self, validation_results: list[CheckResult] | tuple[CheckResult, ...]
    ) -> RepairInstructions:
        return self.build_repair_instructions(validation_results)
