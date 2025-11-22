"""
Validation CLI commands.

Provides commands for validating deletion plans against policies.
"""

import json
import sys

import click

from rmrf.models import Verdict
from rmrf.protection import ProtectionLevelRegistry
from rmrf.store import PlanStore
from rmrf.validator import BuiltinValidator

from ..output import format_bytes, log_error, log_info, print_structured_output
from ..utils import load_plan


@click.command(
    epilog="""
Examples:
  rmrf validate plan-20250107-120000-abc123              # Validate with built-in rules
  rmrf validate plan.json                                # Validate from file
  rmrf validate plan.json --approval-id appr-12345       # With pre-approval
"""
)
@click.argument("plan_id_or_file")
@click.option(
    "--approval-id",
    help="Approval ID if pre-approved",
)
@click.pass_context
def validate(
    ctx: click.Context,
    plan_id_or_file: str,
    approval_id: str | None,
) -> None:
    """
    Validate a deletion plan against built-in safety policies.

    Uses production-ready safety rules including expiration checks, protection
    level limits, risk assessment, and approval requirements.

    Accepts either a plan ID (from the plan store) or a path to a plan JSON file.

    \b
    Examples:
      rmrf validate plan-20250107-120000-abc123
      rmrf validate plan.json
      rmrf validate plan.json --approval-id appr-12345
    """
    json_output = ctx.obj["json_output"]

    try:
        # Load plan
        plan_obj = load_plan(plan_id_or_file)

        # Validate workflow order
        can_proceed, error_msg = plan_obj.can_validate()
        if not can_proceed:
            log_error(f"Cannot validate plan: {error_msg}")
            sys.exit(1)

        # Get protection level
        registry = ProtectionLevelRegistry(load_defaults=True)
        protection_level = registry.require(plan_obj.protection_level)

        # Built-in validation
        if not json_output:
            log_info("Using built-in validation (production-ready)")

        # Check if protection level requires approval
        if protection_level.require_approval and not plan_obj.approved:
            # Mark plan as requiring approval
            try:
                store = PlanStore(auto_create=False)
                if store.exists(plan_obj.plan_id):
                    store.mark_approval_required(plan_obj.plan_id)
                    plan_obj = store.load(plan_obj.plan_id)
                else:
                    plan_obj.requires_approval = True
                    plan_obj.approved = False
            except Exception:
                plan_obj.requires_approval = True
                plan_obj.approved = False

        # Use built-in validator
        validator = BuiltinValidator()
        verdict = validator.validate(plan_obj, protection_level, approval_id=approval_id)

        # Mark plan as validated in store if verdict is ALLOW
        if verdict.verdict == Verdict.ALLOW:
            store = PlanStore(auto_create=True)
            if store.exists(plan_obj.plan_id):
                policy_verdict_data = {
                    "verdict": verdict.verdict.value,
                    "message": verdict.message,
                    "reasons": verdict.reasons,
                }
                store.mark_validated(plan_obj.plan_id, policy_verdict=policy_verdict_data)

        # Output result
        if json_output:
            result = {
                "plan_id": plan_obj.plan_id,
                "valid": verdict.verdict == Verdict.ALLOW,
                "verdict": verdict.verdict.value,
                "message": verdict.message,
                "reasons": verdict.reasons,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            scenario_name = plan_obj.scenario or f"plan {plan_obj.plan_id}"

            # Handle different verdict outcomes
            if verdict.verdict == Verdict.ALLOW:
                reasons_str = f" {'. '.join(verdict.reasons[:3])}." if verdict.reasons else ""
                print_structured_output(
                    verdict="ALLOWED",
                    scenario=scenario_name,
                    summary="approved by safety policy",
                    what_happened=f"Plan {plan_obj.plan_id} validated using built-in safety rules. "
                    f"The plan for {plan_obj.file_count} files ({format_bytes(plan_obj.total_bytes)}) "
                    f"in {plan_obj.environment} environment passed all safety checks.{reasons_str}",
                    why_it_matters="Built-in validation implements production-ready safety rules including expiration checks, "
                    "protection level limits, risk assessment, and approval requirements. "
                    "This ensures safe deletions with comprehensive policy enforcement.",
                    next_steps=[
                        f"Create backup: rmrf stage {plan_obj.plan_id}",
                        f"Execute deletion: rmrf apply {plan_obj.plan_id}",
                        f"Monitor status: rmrf status --plan-id {plan_obj.plan_id}",
                    ],
                    additional_info={
                        "Plan ID": plan_obj.plan_id,
                        "Verdict": verdict.verdict.value,
                        "Environment": plan_obj.environment,
                        "Protection Level": plan_obj.protection_level,
                    },
                )

            elif verdict.verdict == Verdict.DENY:
                # Save denial verdict to store
                try:
                    store = PlanStore(auto_create=False)
                    if store.exists(plan_obj.plan_id):
                        policy_verdict_data = {
                            "verdict": verdict.verdict.value,
                            "message": verdict.message,
                            "reasons": verdict.reasons,
                        }
                        # Update plan with denial verdict
                        plan_obj.policy_verdict = verdict
                        store.save(plan_obj)
                except Exception:
                    pass

                reasons_str = "\n  • " + "\n  • ".join(verdict.reasons) if verdict.reasons else ""
                print_structured_output(
                    verdict="DENIED",
                    scenario=scenario_name,
                    summary="blocked by safety policy",
                    what_happened=f"Plan {plan_obj.plan_id} evaluated and denied by built-in safety policy. "
                    f"The plan to delete {plan_obj.file_count} files ({format_bytes(plan_obj.total_bytes)}) "
                    f"in {plan_obj.environment} environment was blocked. {verdict.message or 'Policy requirements not met.'}",
                    why_it_matters="Policy denial prevents unsafe deletions that violate safety rules. "
                    "This protects critical data and enforces safety-first operations.",
                    next_steps=[
                        "Review policy requirements and denial reasons below",
                        "Adjust plan parameters if appropriate (e.g., reduce scope, change environment)",
                        "Create new plan: rmrf plan <targets> --environment <env>",
                    ],
                    additional_info={
                        "Plan ID": plan_obj.plan_id,
                        "Verdict": verdict.verdict.value,
                        "Environment": plan_obj.environment,
                        **({"Denial Reasons": reasons_str} if verdict.reasons else {}),
                    },
                )
                sys.exit(1)

            elif verdict.verdict == Verdict.REQUIRE_APPROVAL:
                # Save approval requirement to store
                try:
                    store = PlanStore(auto_create=False)
                    if store.exists(plan_obj.plan_id):
                        policy_verdict_data = {
                            "verdict": verdict.verdict.value,
                            "message": verdict.message,
                            "reasons": verdict.reasons,
                        }
                        # Update plan with approval requirement
                        plan_obj.policy_verdict = verdict
                        store.save(plan_obj)
                except Exception:
                    pass

                reasons_str = "\n  • " + "\n  • ".join(verdict.reasons) if verdict.reasons else ""
                print_structured_output(
                    verdict="REQUIRES_APPROVAL",
                    scenario=scenario_name,
                    summary="requires manual approval",
                    what_happened=f"Plan {plan_obj.plan_id} evaluated by built-in safety policy. "
                    f"Deletion of {plan_obj.file_count} files ({format_bytes(plan_obj.total_bytes)}) "
                    f"requires additional approval before proceeding. {verdict.message or ''}",
                    why_it_matters="Approval requirements protect high-risk operations by ensuring human oversight. "
                    "This adds an additional safety gate for operations that exceed automated policy limits.",
                    next_steps=[
                        "Review approval reasons below",
                        "Request approval from authorized approver",
                        "Rerun validation with: rmrf validate <plan> --approval-id <id>",
                    ],
                    additional_info={
                        "Plan ID": plan_obj.plan_id,
                        "Verdict": verdict.verdict.value,
                        "Environment": plan_obj.environment,
                        **({"Approval Reasons": reasons_str} if verdict.reasons else {}),
                    },
                )
                sys.exit(2)

    except json.JSONDecodeError as e:
        log_error(f"Invalid JSON in plan file: {e}")
        sys.exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        sys.exit(1)
