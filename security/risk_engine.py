"""Shared deterministic policy; all executable traffic must clear the Guard."""
from security.schemas import Decision


def decide(findings, results, context, local_attack=False, analysis_only=False):
    if any(f.category in {"inspection_limit", "session_injection", "secret_leak"} for f in findings):
        return Decision.BLOCK, 100
    if any(not r.get('ok') or r.get('status') != 'complete' for r in results) or not results:
        return Decision.BLOCK, 100
    flagged = [r for r in results if r.get('allowed') is not True]
    non_injection = any(not r.get('flags') or set(r.get('flags', [])) - {'injection'} for r in flagged)
    if non_injection or (local_attack and not analysis_only):
        return Decision.BLOCK, 95
    if flagged or local_attack:
        if context.analysis_intent and not context.execution_intent and analysis_only:
            return Decision.REVIEW, 55
        return Decision.BLOCK, 90
    if any(f.severity == 'medium' for f in findings):
        return Decision.REVIEW, 45
    if findings:
        return Decision.WARN, 15
    return Decision.ALLOW, 0
